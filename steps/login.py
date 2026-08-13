"""로그인. 세션을 재사용해 로그인 횟수를 줄인다(캡차 위험 감소)."""

from __future__ import annotations

import mall_selectors as sel


def ensure_logged_in(page, mall_url: str, login_id: str, password: str, log=print) -> None:
    """이미 로그인돼 있으면 아무것도 하지 않고, 아니면 로그인한다."""
    page.goto(mall_url, wait_until="domcontentloaded")
    if _wait_logged_in(page, timeout=4000):
        log("   이미 로그인된 세션을 재사용합니다.")
        return

    page.goto(mall_url.rstrip("/") + sel.Login.URL_PATH, wait_until="domcontentloaded")

    # ⚠ 이미 로그인된 상태로 로그인 페이지에 가면 몰이 홈으로 되돌려보낸다.
    #   그러면 아이디 칸이 없어서 fill()이 30초를 통째로 기다리다 죽는다(실제로 겪음).
    #   칸이 안 보이면 로그인된 것부터 다시 확인한다.
    if not _wait_visible(page, sel.Login.ID_INPUT, timeout=8000):
        if _wait_logged_in(page, timeout=3000):
            log("   이미 로그인되어 있습니다.")
            return
        raise RuntimeError(
            "쇼핑몰 로그인 화면을 열지 못했습니다.\n\n"
            "인터넷 연결을 확인하시고 잠시 뒤 다시 시도해주세요.\n"
            "쇼핑몰 점검 중일 수도 있으니 브라우저에서 접속되는지 확인해주세요."
        )

    page.fill(sel.Login.ID_INPUT, login_id)
    page.fill(sel.Login.PASSWORD_INPUT, password)
    page.press(sel.Login.PASSWORD_INPUT, "Enter")
    page.wait_for_load_state("domcontentloaded")

    if not _wait_logged_in(page, timeout=8000):
        raise RuntimeError(_login_failure_reason(page))


def _wait_logged_in(page, timeout: int) -> bool:
    """로그인 표시가 나타날 때까지 기다린다. 고정 시간 대기보다 느린 화면에 강하다."""
    try:
        page.wait_for_selector(sel.Login.LOGGED_IN_MARKER, timeout=timeout, state="attached")
        return True
    except Exception:
        return False


def _wait_visible(page, selector: str, timeout: int) -> bool:
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        return True
    except Exception:
        return False



def _login_failure_reason(page) -> str:
    """로그인이 안 됐을 때, 쇼핑몰 화면에 실제로 뜬 문구를 읽어 원인을 특정한다.

    무조건 "비밀번호를 확인하세요"라고 하면 캡차·점검·차단일 때 엉뚱한 곳을 헤매게 된다.
    """
    try:
        body = page.locator("body").inner_text()
    except Exception:
        body = ""

    if any(k in body for k in ("자동입력 방지", "보안문자", "캡차", "captcha")):
        return (
            "쇼핑몰이 '자동입력 방지문자' 입력을 요구하고 있습니다.\n\n"
            "로그인 시도가 여러 번 실패하면 나타납니다.\n"
            "브라우저에서 직접 한 번 로그인하신 뒤 다시 실행해주세요."
        )

    if any(k in body for k in ("휴면", "잠금", "정지", "차단")):
        return (
            "쇼핑몰 계정에 문제가 있는 것 같습니다(휴면·잠금 등).\n\n"
            "브라우저에서 직접 로그인해 상태를 확인해주세요."
        )

    # 로그인 폼이 그대로 남아 있으면 계정 정보가 안 맞은 것이다
    if page.locator(sel.Login.ID_INPUT).count() > 0:
        return (
            "아이디 또는 비밀번호가 맞지 않습니다.\n\n"
            "[설정]에서 다시 확인해주세요.\n"
            "대소문자와 앞뒤 공백까지 정확해야 합니다."
        )

    return (
        "쇼핑몰에 로그인하지 못했습니다.\n\n"
        "인터넷 연결을 확인하시고 잠시 뒤 다시 시도해주세요.\n"
        "계속 안 되면 브라우저에서 직접 로그인이 되는지 확인해주세요."
    )


def deposit_balance(page) -> str:
    """헤더에 노출된 보유 예치금 (표시용 문자열)."""
    marker = page.locator(sel.Login.DEPOSIT_BALANCE)
    if marker.count() == 0:
        return ""
    return (marker.first.inner_text() or "").strip()


def deposit_balance_won(page) -> int:
    """보유 예치금을 원 단위 정수로. 못 읽으면 -1."""
    import re

    digits = re.sub(r"[^\d]", "", deposit_balance(page))
    return int(digits) if digits else -1


def _is_logged_in(page) -> bool:
    return page.locator(sel.Login.LOGGED_IN_MARKER).count() > 0
