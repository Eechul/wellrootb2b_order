"""상품 페이지 → 옵션 → 수량 → 장바구니 담기, 그리고 장바구니 → 주문서.

한 라인이 실패해도 나머지는 계속 담고, 실패는 전부 리포트에 남긴다.
장바구니에 모아서 **한 번에 주문**하는 게 이 도구의 핵심이다.
사장님이 지금 상품마다 반복하는 [구매 → 배송지 → 예치금 → 결제]가 1회로 줄어든다.
"""

from __future__ import annotations

import mall_selectors as sel
from dialog import DialogLog
from excel_reader import OrderLine
from report import Report, Status


UNKNOWN = -1  # 장바구니 상태를 읽지 못했다 (0건과 절대 섞으면 안 된다)


def cart_item_count(page, mall_url: str) -> int:
    """장바구니 항목 수. 화면을 못 읽으면 UNKNOWN(-1).

    🚨 결제 여부를 이 값으로 판정하므로, **못 읽은 것을 0으로 돌려주면 안 된다.**
       로그아웃·셀렉터 변경·페이지 오류로 0이 나오면 결제하지 않은 주문이
       '결제 완료'로 이력에 박히고 그 배송지는 영영 빠진다.
    """
    go_to_cart(page, mall_url)

    items = page.locator(sel.Cart.ITEM_CHECKBOX).count()
    if items:
        return items

    # ⚠ 로그아웃 상태의 장바구니도 '비어 있습니다'로 나온다(비회원 장바구니라 당연히 비었다).
    #   그걸 0으로 받으면 세션이 끊겼을 때 "결제 완료"로 오판한다 → 로그인부터 확인한다.
    if page.locator(sel.Login.LOGGED_IN_MARKER).count() == 0:
        return UNKNOWN

    if page.locator(sel.Cart.EMPTY_MARKER).count() > 0:
        return 0
    # 항목도 없고 '비어 있습니다'도 없다 → 장바구니 화면이 아니다
    return UNKNOWN


def clear_cart(page, dialogs: DialogLog, mall_url: str) -> None:
    """장바구니를 비운다. 기존 항목이 우리 발주와 섞여 함께 주문되는 걸 막는다.

    🚨 비웠는지 **반드시 확인**한다. 조용히 실패하면 앞 배송지 상품이
       뒷 배송지 주소로 함께 주문되어 엉뚱한 사람에게 배송된다.
    """
    go_to_cart(page, mall_url)
    if page.locator(sel.Cart.ITEM_CHECKBOX).count() == 0:
        return

    page.evaluate(
        f"""() => document.querySelectorAll('{sel.Cart.ITEM_CHECKBOX}')
                     .forEach(c => {{ c.checked = true; }})"""
    )
    page.evaluate("() => Basket.deleteBasket()")
    page.wait_for_timeout(2500)
    messages = dialogs.take()

    left = cart_item_count(page, mall_url)
    if left != 0:
        why = f" ({' / '.join(messages)})" if messages else ""
        raise RuntimeError(
            f"장바구니를 비우지 못했습니다{why}.\n\n"
            "이대로 진행하면 남아 있는 상품까지 함께 주문됩니다.\n"
            "쇼핑몰에서 장바구니를 직접 비우신 뒤 다시 실행해주세요."
        )


def add_lines_to_cart(page, dialogs: DialogLog, lines: list[OrderLine], report: Report, log=print) -> None:
    for line in lines:
        dialogs.take()  # 이전 라인의 메시지가 섞이지 않게 비운다
        try:
            _add_one(page, dialogs, line)
        except _LineError as e:
            report.add(line.row, line.product_url, e.status, str(e))
        except Exception as e:  # noqa: BLE001 — 한 줄 실패로 전체를 멈추지 않는다
            report.add(line.row, line.product_url, Status.FAILED, _short(e))
        else:
            report.add(line.row, line.product_url, Status.OK)


def _add_one(page, dialogs: DialogLog, line: OrderLine) -> None:
    page.goto(line.product_url, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    if _is_sold_out(page):
        raise _LineError(Status.SOLD_OUT, "품절이거나 판매가 중지된 상품입니다")

    _select_options(page, line.option)

    quantity = page.locator(sel.Product.QUANTITY_INPUT)
    if quantity.count() == 0:
        raise _LineError(Status.PAGE_ERROR, "상품 페이지를 열지 못했습니다. 엑셀의 상품 주소를 확인해주세요")
    quantity.first.fill(str(line.quantity))

    button = page.locator(sel.Product.ADD_TO_CART)
    if button.count() == 0:
        raise _LineError(Status.PAGE_ERROR, "이 상품은 장바구니에 담을 수 없습니다. 쇼핑몰에서 직접 확인해주세요")

    # 담기에 성공하면 몰이 장바구니로 보낸다. 그게 유일하게 믿을 만한 성공 신호다.
    button.first.click()
    try:
        page.wait_for_url("**/order/basket.html*", timeout=15000)
    except Exception:
        raise _LineError(Status.FAILED, _why_failed(dialogs)) from None


def _is_sold_out(page) -> bool:
    sold_out = page.locator(sel.Product.SOLD_OUT_MARKER)
    return sold_out.count() > 0 and sold_out.first.is_visible()


def _select_options(page, option_text: str) -> None:
    """엑셀의 옵션 문자열을 상품의 옵션 select에 채운다.

    옵션이 여러 개면 엑셀에 `/`로 구분해 적는다. 예: `블랙 / L`
    엑셀 옵션 칸이 비어 있으면(또는 `(없음)`이면) 아무것도 고르지 않는다.
    """
    main = page.locator(sel.Product.OPTION_SELECTS)
    addproduct = page.locator(sel.Product.ADDPRODUCT_SELECTS)

    if not option_text:
        # 본품 필수 옵션이 있는데 엑셀이 비었으면 담기에서 몰이 막아준다 → 그때 사유가 잡힌다.
        return

    target = main if main.count() > 0 else addproduct
    count = target.count()
    if count == 0:
        raise _LineError(
            Status.OPTION_MISMATCH,
            f"이 상품에는 선택할 옵션이 없습니다. 엑셀의 옵션 칸을 (없음)으로 바꿔주세요 (지금: {option_text})",
        )

    wanted = [part.strip() for part in option_text.split("/") if part.strip()]
    if len(wanted) != count:
        raise _LineError(
            Status.OPTION_MISMATCH,
            f"옵션을 {count}개 골라야 하는데 엑셀에는 {len(wanted)}개만 적혀 있습니다. 슬래시(/)로 구분해 적어주세요",
        )

    for i, value in enumerate(wanted):
        try:
            target.nth(i).select_option(label=value)
        except Exception:
            available = [t.strip() for t in target.nth(i).locator("option").all_inner_texts() if t.strip()]
            raise _LineError(
                Status.OPTION_MISMATCH,
                f"'{value}' 옵션이 없습니다. 고를 수 있는 옵션: {', '.join(available)}",
            ) from None


def _why_failed(dialogs: DialogLog) -> str:
    """담기가 실패했을 때 몰이 띄운 alert 메시지가 곧 사유다 (예: 필수 옵션 미선택)."""
    pending = dialogs.take()
    if pending:
        return " / ".join(pending)
    return "장바구니에 담기지 않았습니다. 쇼핑몰에서 직접 확인해주세요"


def go_to_cart(page, mall_url: str) -> None:
    page.goto(mall_url.rstrip("/") + sel.Cart.URL_PATH, wait_until="domcontentloaded")
    page.wait_for_timeout(800)


def start_order(page, mall_url: str) -> None:
    """장바구니에서 전체상품주문 → 주문서."""
    go_to_cart(page, mall_url)
    page.click(sel.Cart.ORDER_ALL)
    page.wait_for_url(f"**{sel.OrderForm.URL_MARKER}*", timeout=20000)
    page.wait_for_timeout(1500)


class _LineError(Exception):
    def __init__(self, status: Status, message: str) -> None:
        super().__init__(message)
        self.status = status


def _short(e: Exception) -> str:
    """담기 중 난 예상 밖 오류를 짧고 읽을 수 있게 줄인다."""
    if "Timeout" in type(e).__name__:
        return "쇼핑몰 응답이 느려 담지 못했습니다"
    first = str(e).splitlines()[0][:70] if str(e) else type(e).__name__
    return f"담는 중 문제가 생겼습니다 ({first})"
