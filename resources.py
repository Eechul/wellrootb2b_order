"""아이콘·이미지 같은 동봉 파일의 경로를 찾아준다.

PyInstaller onefile은 동봉 파일을 실행할 때마다 임시폴더(`sys._MEIPASS`)에 풀어놓는다.
설정 파일(exe 옆)과는 위치가 **다르다** — 이걸 헷갈리면 개발 중엔 되는데 exe에서만 그림이 안 뜬다.

  · 동봉 파일(읽기 전용): 여기 `asset()` — _MEIPASS
  · 설정·이력(쓰기):      app.py의 `app_dir()` — exe 옆
"""

from __future__ import annotations

import sys
from pathlib import Path

ASSETS_DIR = "assets"


def asset(name: str) -> Path | None:
    """`assets/<name>` 의 실제 경로. 없으면 None (그림이 없어도 앱은 돌아야 한다)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    path = base / ASSETS_DIR / name
    return path if path.exists() else None
