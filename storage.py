r"""설정·이력·세션을 어디에 둘지 한 곳에서 정한다.

## 왜 exe 옆이 아닌가

사장님이 exe를 바탕화면에 두면 설정·이력 파일이 **바탕화면에 흩뿌려진다.**
지저분해서 지우면 계정이 날아가고, 이력을 지우면 **중복 발주 방지가 풀린다.**
`history.jsonl`에는 고객 이름·전화·주소가 들어 있어서 눈에 띄는 곳에 두면 안 된다.
게다가 `Program Files`에 두면 쓰기 권한이 없어 아예 저장이 안 된다.

## 그래서

    %LOCALAPPDATA%\WellrootOrder\      ← 기본. 어디에 exe를 두든 항상 쓰기 가능하고,
                                          윈도우 사용자별로 분리되며, exe를 옮겨도 유지된다.

**단, exe 옆에 `config.json`이 이미 있으면 그 폴더를 쓴다(휴대용 모드).**
USB에 넣어 다니거나, 예전 방식으로 쓰던 사용자를 위한 것이다. 마이그레이션이 필요 없다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_FOLDER = "WellrootOrder"  # %LOCALAPPDATA% 아래 폴더명. ASCII로 유지할 것
PORTABLE_MARKER = "config.json"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """설정·이력·세션을 둘 폴더. 없으면 만들어서 돌려준다."""
    if not is_frozen():
        # 개발 중에는 프로젝트 폴더를 그대로 쓴다 (실제 배포 동작과 헷갈리지 않게 selftest가 알려준다)
        return Path(__file__).parent

    beside_exe = Path(sys.executable).parent
    if (beside_exe / PORTABLE_MARKER).exists():
        return beside_exe

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    target = (Path(base) if base else Path.home()) / APP_FOLDER
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        return beside_exe  # 만들 수 없으면 예전 방식으로라도 동작하게
    return target


def is_portable() -> bool:
    """휴대용 모드(exe 옆 저장)인지."""
    return is_frozen() and app_dir() == Path(sys.executable).parent


APP_DIR = app_dir()
CONFIG_PATH = APP_DIR / "config.json"
HISTORY_PATH = APP_DIR / "history.jsonl"
SESSION_PATH = APP_DIR / "session.json"
ERROR_LOG = APP_DIR / "error.log"
SELFTEST_LOG = APP_DIR / "selftest.log"
