"""주문서 — 배송지 입력 + 예치금 '사용'까지.

⛔ 결제하기(#btn_payment)는 누르지 않는다. 여기까지가 자동화의 끝이고 사람이 확인 후 결제한다.
   (설계 원칙 — .claude/memory/mvp-browser-automation.md. 임의로 결제 클릭을 추가하지 말 것)
"""

from __future__ import annotations

import re

import mall_selectors as sel
from excel_reader import OrderGroup

# 주문서 앞자리 select에 실제로 들어있는 값(실측). 하이픈 없이 적힌 번호를 나눌 때 쓴다.
# 긴 것부터 맞춰야 '010'보다 '0505'를 먼저 잡는다.
PHONE_PREFIXES = (
    "0502", "0503", "0504", "0505", "0506", "0507", "0508",
    "031", "032", "033", "041", "042", "043", "044",
    "051", "052", "053", "054", "055", "061", "062", "063", "064",
    "010", "011", "016", "017", "018", "019", "070", "050", "02",
)


def fill_shipping(page, group: OrderGroup, log=print) -> None:
    """배송지를 '새로 입력'으로 바꾸고 엑셀 값을 채운다."""
    new_address = page.locator(sel.OrderForm.SHIPPING_NEW)
    if new_address.count() > 0:
        new_address.first.check()
        page.wait_for_timeout(500)

    _fill(page, sel.OrderForm.RECEIVER, group.receiver, "수취인", log)
    _fill_address(page, group, log)
    _fill_phone(page, sel.OrderForm.PHONE_PARTS, group.phone, "휴대폰번호", log)
    _fill_phone(page, sel.OrderForm.TEL_PARTS, group.tel, "전화번호", log)
    _fill_memo(page, group.memo, log)


def _fill_address(page, group: OrderGroup, log=print) -> None:
    """우편번호·기본주소는 readonly다. 카카오 우편번호 위젯만 값을 넣을 수 있는 구조.

    위젯은 중첩 iframe(postcode.map.kakao.com) 안에 있고 DOM이 우리 통제 밖에서 바뀐다.
    위젯이 하는 일은 결국 이 세 칸을 채우는 것뿐이므로 값을 직접 넣고 **읽어서 검증**한다.
    잘못된 주소가 그대로 결제되는 걸 막는 건 마지막 사람 확인 단계다(결제 전 정지 원칙).
    """
    _set_readonly(page, sel.OrderForm.ZIPCODE, group.zipcode, "우편번호", log)
    _set_readonly(page, sel.OrderForm.ADDRESS, group.address, "주소", log)
    _fill(page, sel.OrderForm.ADDRESS_DETAIL, group.address_detail, "상세주소", log)

    written = {
        "우편번호": page.locator(sel.OrderForm.ZIPCODE).first.input_value(),
        "기본주소": page.locator(sel.OrderForm.ADDRESS).first.input_value(),
    }
    expected = {"우편번호": group.zipcode, "기본주소": group.address}
    for label, want in expected.items():
        if want and written[label].strip() != want.strip():
            raise RuntimeError(
                f"{label}가 주문서에 제대로 입력되지 않았습니다.\n\n"
                f"엑셀에 적힌 값: {want}\n"
                f"주문서에 들어간 값: {written[label] or '(비어 있음)'}\n\n"
                "쇼핑몰 화면이 바뀌었을 수 있습니다.\n"
                "주문서에서 [주소검색] 버튼으로 직접 입력하신 뒤 결제해주세요."
            )
    log(f"   배송지: {written['우편번호']} {written['기본주소']} {group.address_detail}".rstrip())


def _set_readonly(page, selector: str, value: str, label: str, log=print) -> None:
    """readonly 입력칸에 값을 넣는다. 위젯이 채운 것과 동일하게 보이도록 이벤트도 발생시킨다."""
    if not value:
        return
    target = page.locator(selector)
    if target.count() == 0:
        log(f"   · 주문서에서 {label} 칸을 찾지 못했습니다 — 직접 입력해주세요.")
        return
    target.first.evaluate(
        """(el, v) => {
            el.removeAttribute('readonly');
            el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.setAttribute('readonly', '');
        }""",
        value,
    )


def apply_deposit(page, log=print) -> tuple[int, int, int]:
    """예치금 '사용' 버튼을 눌러 보유 예치금을 결제에 적용한다.

    이 몰은 "예치금 구매를 제외한 모든 제품은 예치금으로만 결제 가능"하다.
    몰은 min(보유잔액, 주문금액)을 넣어주므로, 예치금이 충분하면 **남은 결제금액이 0이 된다**
    (몰 안내 그대로: "예치금으로만 결제할 경우, 결제금액이 0으로 보여지는 것은 정상").
    → **적용 후 결제금액이 0보다 크면 그만큼 예치금이 모자란다.**

    반환: (적용된 예치금, 적용 전 주문금액, 적용 후 남은 결제금액). 못 읽으면 -1.
    """
    total_before = _won(page, sel.OrderForm.TOTAL_PRICE)

    button = page.locator(sel.OrderForm.DEPOSIT_USE_ALL)
    if button.count() == 0:
        log("   · 주문서에서 예치금 [사용] 버튼을 찾지 못했습니다 — 직접 눌러주세요.")
        return -1, total_before, -1

    button.first.click()
    page.wait_for_timeout(1500)

    applied = _to_won(page.locator(sel.OrderForm.DEPOSIT_INPUT).first.input_value())
    total_after = _won(page, sel.OrderForm.TOTAL_PRICE)
    return applied, total_before, total_after


def _won(page, selector: str) -> int:
    target = page.locator(selector)
    if target.count() == 0:
        return -1
    return _to_won(target.first.inner_text())


def _to_won(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else -1


def _fill(page, selector: str, value: str, label: str, log=print) -> None:
    """엑셀 값을 그대로 넣는다. **빈칸이면 화면도 비운다.**

    주문서는 '새로 입력'을 골라도 기본배송지 값이 남아 있다.
    빈칸을 건너뛰면 앞사람의 연락처·상세주소가 그대로 남아 다른 사람에게 간다.
    엑셀을 진실의 원천으로 두는 게 안전하다.
    """
    target = page.locator(selector)
    if target.count() == 0:
        if value:
            log(f"   · 주문서에서 {label} 칸을 찾지 못했습니다 — 직접 입력해주세요.")
        return
    target.first.fill(value)


def _fill_phone(page, parts_selectors: tuple[str, str, str], phone: str, label: str, log=print) -> None:
    """번호를 3칸(앞자리 select + 텍스트 2칸)에 나눠 넣는다.

    엑셀이 빈칸이면 뒤 두 칸을 비워 번호를 없앤다.
    (앞자리 select에는 빈 항목이 없어서 select 자체는 기본값으로 남는다 — 번호가 비면 그만이다)
    """
    head_sel, mid_sel, tail_sel = parts_selectors

    # 🚨 무엇을 하든 **먼저 비운다.**
    #   중간에 어떤 이유로 빠져나가도 앞 수령인의 번호가 남으면 안 된다.
    #   (주소는 검증해서 멈추는데 연락처만 조용히 남던 구멍이었다)
    _fill(page, mid_sel, "", label, log)
    _fill(page, tail_sel, "", label, log)
    if not phone:
        return

    parts = split_phone(phone)
    if parts is None:
        log(f"   · {label} '{phone}' 형식을 알아볼 수 없습니다. 주문서에서 직접 입력해주세요.")
        return

    head, mid, tail = parts

    head_select = page.locator(head_sel)
    if head_select.count() > 0:
        try:
            head_select.first.select_option(head)
        except Exception:
            log(f"   · {label} 앞자리 '{head}'는 쇼핑몰이 지원하지 않습니다. 주문서에서 직접 입력해주세요.")
            return
    _fill(page, mid_sel, mid, label, log)
    _fill(page, tail_sel, tail, label, log)

    # 넣은 값이 실제로 들어갔는지 확인 — 주소와 같은 기준을 연락처에도 적용한다
    written = _read(page, mid_sel) + _read(page, tail_sel)
    if written and written != mid + tail:
        raise RuntimeError(
            f"{label}가 주문서에 제대로 입력되지 않았습니다.\n\n"
            f"엑셀에 적힌 값: {phone}\n"
            f"주문서에 들어간 값: {_read(page, head_sel)}-{_read(page, mid_sel)}-{_read(page, tail_sel)}\n\n"
            "주문서에서 직접 확인하고 고친 뒤 결제해주세요."
        )


def _read(page, selector: str) -> str:
    target = page.locator(selector)
    return target.first.input_value() if target.count() else ""


def split_phone(phone: str) -> tuple[str, str, str] | None:
    """'010-1234-5678' → ('010', '1234', '5678'). 하이픈이 없어도 접두사로 나눈다."""
    chunks = [c for c in re.split(r"\D+", phone) if c]
    if len(chunks) == 3:
        return chunks[0], chunks[1], chunks[2]

    digits = "".join(chunks)
    for prefix in PHONE_PREFIXES:
        if digits.startswith(prefix) and len(digits) > len(prefix) + 4:
            rest = digits[len(prefix) :]
            return prefix, rest[:-4], rest[-4:]
    return None


def _fill_memo(page, memo: str, log=print) -> None:
    """배송 메시지는 select(정형 문구) + textarea 조합이고, textarea는 select가 제어한다.

    ⚠ 몰이 **최근 입력한 메모를 기본값으로 미리 넣어둔다**(실측: "(최근 입력) 4층 현관 문앞...").
      비우지 않으면 엉뚱한 배송메모가 다른 수령인에게 그대로 간다.

    select를 먼저 맞춘 뒤 textarea를 채운다 — 위젯을 거스르지 않는 게 안전하다.
    엑셀이 빈칸이면 '-- 메시지 선택 --'으로 되돌리고 textarea도 비운다.
    """
    _pick_memo_option(page, "직접" if memo else "선택")
    _set_text(page, "#omessage", memo, "배송메모", log)

    written = page.locator("#omessage")
    if written.count() and written.first.input_value().strip() != memo.strip():
        log("   · 배송메모가 제대로 입력되지 않았습니다 — 주문서에서 확인해주세요.")


def _pick_memo_option(page, keyword: str) -> None:
    select = page.locator("#omessage_select")
    if select.count() == 0:
        return
    try:
        labels = [t.strip() for t in select.first.locator("option").all_inner_texts()]
        pick = next((t for t in labels if keyword in t), None)
        if pick:
            select.first.select_option(label=pick)
            page.wait_for_timeout(400)
    except Exception:
        pass  # 못 고르면 아래에서 값을 직접 넣는다


def _set_text(page, selector: str, value: str, label: str, log=print) -> None:
    """스킨 JS가 제어하는 칸에 값을 넣는다. 숨겨져 있거나 잠겨 있어도 동작한다."""
    target = page.locator(selector)
    if target.count() == 0:
        if value:
            log(f"   · 주문서에서 {label} 칸을 찾지 못했습니다 — 직접 입력해주세요.")
        return
    target.first.evaluate(
        """(el, v) => {
            el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )
