"""브라우저 실행 — 이미 설치된 Chrome/Edge를 쓴다.

exe로 배포할 때 Playwright의 브라우저(크로미움 한 벌만 200MB 남짓)를 같이 넣지 않기 위함이다.
Edge는 윈도우에 기본 탑재라 Chrome이 없는 PC에서도 폴백이 있다.
셋 다 실패하면 사람이 읽을 수 있는 안내를 낸다.
"""

from __future__ import annotations

# 앞에서부터 시도한다. None은 Playwright가 받아둔 크로미움(개발 PC에는 있다).
CHANNELS = ("chrome", "msedge", None)


def launch(playwright, headless: bool, slow_mo: int, preferred: str | None = None):
    """설치된 브라우저로 실행하고 (browser, 사용한 채널)을 돌려준다."""
    order = [preferred] + [c for c in CHANNELS if c != preferred] if preferred else list(CHANNELS)

    problems = []
    for channel in order:
        try:
            browser = playwright.chromium.launch(
                channel=channel, headless=headless, slow_mo=slow_mo
            )
        except Exception as e:
            problems.append(f"{channel or '내장 크로미움'}: {str(e).splitlines()[0][:80]}")
            continue
        return browser, (channel or "내장 크로미움")

    raise RuntimeError(
        "브라우저를 실행하지 못했습니다. 크롬(또는 엣지)이 설치되어 있는지 확인해주세요.\n"
        + "\n".join(f"  - {p}" for p in problems)
    )
