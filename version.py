"""앱 버전. 자동 업데이트가 이 값을 서버의 최신 버전과 비교한다.

배포할 때마다 올린다. 형식은 `major.minor.patch` 숫자만 — 비교가 단순해야 한다.
"""

VERSION = "0.1.3"
APP_NAME = "웰루트 발주 도우미"

# 문의 창구 — 창 아래 [문의하기]가 이 주소를 연다.
# 바꾸면 배포된 앱에도 반영되므로, 링크가 살아 있는지 확인하고 올릴 것.
SUPPORT_URL = "https://open.kakao.com/o/gHDi6BIi"
SUPPORT_LABEL = "문의하기"
SUPPORT_HINT = "· 자동화 문의"

# 자동 업데이트 매니페스트 주소.
# 🚨 설정 파일이 아니라 **코드에 박아둔다.** 사장님이 처음 설치하면 config.json에
#   update_url 키가 없어서, 설정에만 의존하면 신규 사용자는 영원히 업데이트가 안 된다.
#   (config.json에 update_url이 있으면 그쪽이 우선 — 테스트용 우회로로 쓴다)
#   `releases/latest/download/...` 는 **항상 최신 릴리스**의 자산을 가리킨다.
#   버전을 URL에 박지 않으므로 새 릴리스를 올리기만 하면 구버전 앱이 알아서 찾아온다.
DEFAULT_UPDATE_URL = (
    "https://github.com/Eechul/wellrootb2b_order/releases/latest/download/update.json"
)


def as_tuple(text: str) -> tuple[int, ...]:
    """'1.2.10' → (1, 2, 10). 숫자가 아닌 조각은 0으로 본다."""
    parts = []
    for chunk in (text or "").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str = VERSION) -> bool:
    return as_tuple(candidate) > as_tuple(current)
