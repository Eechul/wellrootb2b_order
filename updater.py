"""자동 업데이트 — 서버의 update.json을 보고 새 버전이면 받아서 교체한다.

## 서버에 올려둘 파일 (update.json)

```json
{
  "version": "0.2.0",
  "url": "https://.../WellrootOrder-0.2.0.exe",
  "sha256": "abc123...",
  "notes": "옵션 상품 지원, 배송메모 오류 수정"
}
```

`sha256`은 넣기를 권한다 — 다운로드가 깨졌는지, 엉뚱한 파일을 받았는지 잡아준다.
없으면 검증을 건너뛴다.

## 왜 배치 파일로 교체하나

윈도우는 **실행 중인 exe를 덮어쓸 수 없다.** 그래서 새 파일을 임시폴더에 받아둔 뒤,
"앱이 끝나기를 기다렸다가 → 교체하고 → 다시 실행하는" 배치를 띄우고 앱은 스스로 종료한다.

## 주의

- exe가 `Program Files` 안에 있으면 교체에 관리자 권한이 필요하다.
  **바탕화면이나 사용자 폴더에 두고 쓰는 것을 전제로 한다.**
- 개발 중(python app.py)에는 아무것도 하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from version import VERSION, is_newer

USER_AGENT = "WellrootOrder-Updater"


@dataclass
class Update:
    version: str
    url: str
    notes: str = ""
    sha256: str = ""


def is_frozen() -> bool:
    """PyInstaller로 묶인 exe로 실행 중인가."""
    return getattr(sys, "frozen", False)


def current_exe() -> Path:
    return Path(sys.executable if is_frozen() else __file__).resolve()


def check(manifest_url: str, timeout: int = 8) -> Update | None:
    """새 버전이 있으면 Update, 없거나 확인 실패면 None.

    업데이트 확인 실패로 앱이 못 뜨면 안 되므로 어떤 오류도 조용히 삼킨다.
    """
    if not manifest_url:
        return None
    try:
        request = urllib.request.Request(manifest_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    version = str(data.get("version", "")).strip()
    url = str(data.get("url", "")).strip()
    if not version or not url or not is_newer(version, VERSION):
        return None
    return Update(version, url, str(data.get("notes", "")), str(data.get("sha256", "")).lower())


def download(update: Update, progress=None, timeout: int = 120) -> Path:
    """새 실행파일을 임시폴더로 받는다. sha256이 있으면 검증한다."""
    target = Path(tempfile.gettempdir()) / f"WellrootOrder-{update.version}.exe"
    digest = hashlib.sha256()

    request = urllib.request.Request(update.url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with target.open("wb") as f:
            while chunk := response.read(256 * 1024):
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)

    if update.sha256 and digest.hexdigest() != update.sha256:
        target.unlink(missing_ok=True)
        raise RuntimeError(
            "내려받은 파일이 손상되었습니다(체크섬 불일치). 잠시 후 다시 시도해주세요."
        )
    return target


def apply_and_restart(new_exe: Path) -> None:
    """앱 종료를 기다렸다가 교체하고 다시 실행하는 배치를 띄우고, 이 프로세스는 끝낸다.

    자기 교체는 **윈도우에서만** 구현되어 있다. 확인·다운로드까지는 어느 OS에서나 동작한다.
    """
    if sys.platform != "win32":
        raise RuntimeError(
            "이 OS에서는 자동 교체를 지원하지 않습니다.\n"
            f"내려받은 파일을 직접 교체해주세요: {new_exe}"
        )
    if not is_frozen():
        raise RuntimeError("개발 모드에서는 자동 교체를 하지 않습니다.")

    target = current_exe()
    backup = target.with_suffix(".exe.old")
    script = Path(tempfile.gettempdir()) / f"wellroot_update_{os.getpid()}.ps1"

    # ⚠ 배치(.bat)가 아니라 PowerShell을 쓰는 이유:
    #   실행파일 이름이 한글이라 cmd의 ANSI 코드페이지에 의존하면 사용자 윈도우 언어에 따라 깨진다.
    #   PowerShell은 BOM 붙은 UTF-8을 지역 설정과 무관하게 제대로 읽는다.
    script.write_text(
        f"""$ErrorActionPreference = 'SilentlyContinue'
$pid_ = {os.getpid()}
$target = '{target}'
$backup = '{backup}'
$new    = '{new_exe}'

# 앱이 완전히 끝날 때까지 기다린다 (실행 중인 exe는 덮어쓸 수 없다)
for ($i = 0; $i -lt 60; $i++) {{
    if (-not (Get-Process -Id $pid_ -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Seconds 1
}}
Start-Sleep -Milliseconds 500

if (Test-Path -LiteralPath $backup) {{ Remove-Item -LiteralPath $backup -Force }}
if (Test-Path -LiteralPath $target) {{ Move-Item -LiteralPath $target -Destination $backup -Force }}
Move-Item -LiteralPath $new -Destination $target -Force

if (-not (Test-Path -LiteralPath $target)) {{
    # 교체 실패 — 원래 것으로 되돌린다
    Move-Item -LiteralPath $backup -Destination $target -Force
}}
Start-Process -FilePath $target
Remove-Item -LiteralPath $PSCommandPath -Force
""",
        encoding="utf-8-sig",  # BOM 필수 — 없으면 PowerShell이 한글을 깨뜨릴 수 있다
    )

    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — 부모가 죽어도 살아남아야 한다
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
         "-File", str(script)],
        creationflags=0x00000008 | 0x00000200,
        close_fds=True,
    )
