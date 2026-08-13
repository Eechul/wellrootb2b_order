"""발주 실행의 본체. CLI(order.py)와 GUI(app.py)가 이 하나를 같이 쓴다.

화면에 찍고 사람을 기다리는 부분만 콜백으로 빼놨다:
  log(str)                     — 진행 상황 한 줄
  ask_payment(i, total, fails) — 결제를 사람에게 넘기고 "next" | "quit" 을 받는다
                                 fails: 이번 주문에서 담기지 못한 라인(결제 전에 보여줘야 한다)

이렇게 나눠야 CLI의 input()과 GUI의 [결제했음] 버튼이 같은 흐름을 공유한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import browser as browser_launcher
import steps
from dialog import DialogLog
from excel_reader import OrderGroup
from history import STATUS_PAID, STATUS_PREPARED, History, group_key, order_fingerprint
from report import Report


@dataclass
class RunResult:
    total_groups: int = 0
    prepared: int = 0
    paid: int = 0
    skipped: int = 0
    unverified: int = 0  # 결제 여부를 확인하지 못한 건
    stopped: bool = False
    error: str = ""
    report: Report = field(default_factory=Report)

    @property
    def ok(self) -> bool:
        return not self.error and not self.report.failures


def run_orders(
    groups: list[OrderGroup],
    excel_path: str,
    config: dict,
    *,
    log,
    ask_payment,
    ask_clear_cart=None,
    history_path: str | Path,
    session_path: str | Path,
    clear_cart: bool = False,
    force: bool = False,
    headless: bool = False,
) -> RunResult:
    """배송지별로 순차 처리한다. 주문 1건에 배송지 1곳이라 배송지 수만큼 주문이 나온다."""
    from playwright.sync_api import sync_playwright

    mall_url = config["mall_url"]
    session_file = Path(session_path)
    history = History(history_path)   # 어떤 손상이든 예외를 던지지 않는다
    # 파일 바이트가 아니라 발주 '내용'으로 지문을 잡는다 — 엑셀을 다시 저장해도 유지된다
    excel_hash = order_fingerprint(groups)
    excel_name = Path(excel_path).name

    result = RunResult(total_groups=len(groups))
    result.report = Report(log=log)
    report = result.report

    # 이력이 사라졌는데 아무 말이 없으면 중복 방지가 풀린 걸 아무도 모른다
    log(f"지금까지 결제가 확인된 배송지 {history.paid_count}곳을 기억하고 있습니다.")
    if history.unreadable:
        log("⚠ 발주 이력을 읽지 못했습니다 — 이미 결제한 배송지가 다시 준비될 수 있습니다.")
    elif history.broken_lines:
        log(f"⚠ 발주 이력 {history.broken_lines}줄을 읽지 못했습니다 — "
            "이미 결제한 배송지가 다시 준비될 수 있으니 주문 내용을 꼭 확인해주세요.")

    already = sum(1 for g in groups if history.is_paid(excel_hash, group_key(g)))
    if already and not force:
        log(f"이 엑셀에서 이미 결제를 마친 배송지 {already}곳은 건너뜁니다.")

    with sync_playwright() as p:
        try:
            browser, channel = browser_launcher.launch(
                p,
                headless=headless or config.get("headless", False),
                slow_mo=config.get("slow_mo_ms", 0),
                preferred=config.get("browser_channel"),
            )
        except RuntimeError as e:
            result.error = str(e)
            return result

        log(f"{channel}(으)로 실행합니다.")
        context = browser.new_context(
            storage_state=str(session_file) if session_file.exists() else None
        )
        page = context.new_page()
        dialogs = DialogLog(page)

        try:
            log("쇼핑몰에 로그인하는 중...")
            steps.ensure_logged_in(page, mall_url, config["login"]["id"], config["login"]["password"])
            context.storage_state(path=str(session_file))
            balance = steps.deposit_balance(page)
            log(f"로그인 완료 · 보유 예치금 {balance}" if balance else "로그인 완료")

            existing = steps.cart_item_count(page, mall_url)
            if existing == steps.UNKNOWN:
                result.error = (
                    "쇼핑몰 장바구니 화면을 읽지 못했습니다.\n\n"
                    "로그인이 풀렸거나 쇼핑몰 화면이 바뀌었을 수 있습니다.\n"
                    "브라우저에서 장바구니가 정상적으로 열리는지 확인한 뒤 다시 실행해주세요."
                )
                return result
            if existing and not clear_cart:
                # 손품을 줄이려고 쓰는 도구인데, 앱을 껐다 켜고 몰에 들어가 비우게 하면 안 된다.
                # 물어볼 수 있으면 그 자리에서 비운다.
                if ask_clear_cart and ask_clear_cart(existing):
                    log(f"   장바구니에 있던 {existing}건을 비웁니다.")
                    steps.clear_cart(page, dialogs, mall_url)
                else:
                    result.error = (
                        f"쇼핑몰 장바구니에 이미 {existing}건이 담겨 있습니다.\n\n"
                        "그대로 진행하면 그 상품까지 함께 주문됩니다.\n"
                        "쇼핑몰에서 장바구니를 비우신 뒤 다시 실행해주세요."
                    )
                    return result

            for index, group in enumerate(groups, start=1):
                key = group_key(group)
                log("")
                log(f"── 주문 {index}/{len(groups)} — {group.receiver} ({group.tel})")

                if history.is_paid(excel_hash, key) and not force:
                    log("   이미 결제를 마친 배송지라 건너뜁니다.")
                    result.skipped += 1
                    continue

                leftover = steps.cart_item_count(page, mall_url)
                if leftover == steps.UNKNOWN:
                    result.error = (
                        "쇼핑몰 장바구니 화면을 읽지 못해 중단했습니다.\n\n"
                        "로그인이 풀렸을 수 있습니다. 다시 실행해주세요.\n"
                        "이미 결제를 마친 배송지는 알아서 건너뜁니다."
                    )
                    result.stopped = True
                    return result
                if leftover:
                    log(f"   장바구니에 남아 있던 {leftover}건을 비웁니다.")
                    steps.clear_cart(page, dialogs, mall_url)

                before = len(report.results)
                steps.add_lines_to_cart(page, dialogs, group.lines, report, log=log)
                group_results = report.results[before:]
                failures = [r for r in group_results if not r.ok]
                if not any(r.ok for r in group_results):
                    log("   ❌ 담긴 상품이 하나도 없어 이 주문은 건너뜁니다.")
                    continue

                steps.start_order(page, mall_url)
                steps.fill_shipping(page, group, log=log)
                applied, total_before, total_after = steps.apply_deposit(page)
                result.prepared += 1
                rows = [line.row for line in group.lines]
                history.record(excel_hash, excel_name, key, group.receiver, rows, STATUS_PREPARED)

                shortage = _deposit_message(log, applied, total_before, total_after)
                if shortage:
                    result.error = shortage
                    result.stopped = True
                    return result

                if failures:
                    # 🚨 빠진 상품을 **결제 전에** 알려야 한다. 결제가 다 끝난 뒤 요약하면
                    #   이미 일부만 주문된 상태가 되어 되돌릴 수 없다.
                    log(f"   ⚠ 이 주문에서 {len(failures)}건이 빠졌습니다:")
                    for r in failures:
                        log(f"      {r.row}행 {r.status.value}" + (f" — {r.detail}" if r.detail else ""))
                log(f"   ✅ 주문 {index}/{len(groups)} 준비 완료 — 결제는 하지 않았습니다.")
                answer = ask_payment(index, len(groups), failures)

                # 카페24는 주문이 완료되면 장바구니를 비운다 → 결제 여부를 이걸로 판정한다.
                # 🚨 화면을 못 읽었으면(UNKNOWN) 절대 '결제됨'으로 기록하지 않는다.
                #    잘못 기록하면 재실행 때 건너뛰어 그 배송지가 영영 누락된다.
                after = steps.cart_item_count(page, mall_url)
                if after == 0:
                    history.record(excel_hash, excel_name, key, group.receiver, rows, STATUS_PAID)
                    result.paid += 1
                    log("   결제 확인됨 ✓")
                elif after == steps.UNKNOWN:
                    result.unverified += 1
                    log("   ⚠ 결제 여부를 확인하지 못했습니다 — 쇼핑몰 주문내역에서 직접 확인해주세요.")
                    log("      (확인 못 한 건은 이력에 남기지 않으므로 다시 실행하면 또 준비됩니다)")
                else:
                    log("   ⚠ 아직 결제가 안 된 것 같습니다(장바구니가 그대로입니다).")

                if answer == "quit":
                    result.stopped = True
                    log("\n중단했습니다.")
                    break

            return result

        except RuntimeError as e:
            # 우리가 직접 만든 안내 문구는 그대로 보여준다
            result.error = str(e)
            return result
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 사람이 읽을 수 있게 돌려준다
            result.error = _friendly_error(e)
            return result
        finally:
            context.close()
            browser.close()


def _friendly_error(e: Exception) -> str:
    """예상 못 한 오류를 사용자가 이해할 수 있는 말로 바꾼다.

    사장님에게 `TimeoutError: Locator.click: Timeout 30000ms exceeded`를 보여줘도 할 수 있는 게 없다.
    무엇을 하면 되는지 알려주고, 원인은 담당자에게 전달할 수 있도록 뒤에 한 줄만 붙인다.
    """
    name = type(e).__name__
    first = (str(e).splitlines()[0][:150] if str(e) else name)

    if "Timeout" in name:
        guide = (
            "쇼핑몰 응답이 너무 느려 중단했습니다.\n"
            "인터넷 연결을 확인하시고 잠시 뒤 다시 시도해주세요."
        )
    elif "Target" in name or "closed" in first.lower():
        guide = (
            "브라우저 창이 닫혀 작업을 이어갈 수 없습니다.\n"
            "작업이 끝날 때까지 브라우저 창을 닫지 말아주세요."
        )
    else:
        guide = (
            "예상하지 못한 문제로 중단했습니다.\n"
            "잠시 뒤 다시 시도해보시고, 계속 같은 문제가 생기면 담당자에게 알려주세요."
        )
    return f"{guide}\n\n(원인: {first})"


def _deposit_message(log, applied: int, total_before: int, total_after: int) -> str:
    """예치금 적용 결과를 알리고, 부족하면 사유 문구를 돌려준다(충분하면 빈 문자열)."""
    if applied < 0 or total_after < 0:
        log("   · 금액을 읽지 못했습니다 — 주문서에서 직접 확인해주세요.")
        return ""

    log(f"   주문금액 {total_before:,}원 / 예치금 적용 {applied:,}원")
    if total_after <= 0:
        return ""

    return (
        f"예치금이 {total_after:,}원 부족합니다.\n"
        "이 쇼핑몰은 예치금으로만 결제되기 때문에 이대로는 결제할 수 없습니다.\n"
        "예치금을 충전하신 뒤 같은 엑셀로 다시 실행해주세요. 이미 결제를 마친 배송지는 알아서 건너뜁니다."
    )
