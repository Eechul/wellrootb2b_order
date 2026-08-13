"""설정 파일 읽기/쓰기. 비밀번호는 OS가 제공하는 보안 저장소에 맡긴다.

거래처 사장님 PC에 배포되므로 비밀번호를 평문으로 두지 않는다. 추가 패키지 없이 OS 기능만 쓴다.

- **윈도우**: DPAPI(`CryptProtectData`). 윈도우 사용자 계정에 묶여 암호화되므로
  설정 파일을 다른 PC로 복사해도 풀리지 않는다.
- **맥**: 키체인(`security` 명령). 설정 파일에는 자리표시자만 남는다.
- **그 외**: 저장하지 않는다. 평문으로 남기느니 매번 입력받는 쪽이 낫다.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_MALL_URL = "https://wellrootb2b.com"

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# 맥 키체인 항목 이름
KEYCHAIN_SERVICE = "WellrootOrder"
KEYCHAIN_ACCOUNT = "mall-login"
KEYCHAIN_TOKEN = "keychain"  # 설정 파일에는 이 자리표시자만 저장된다

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes


if IS_WINDOWS:

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes) -> "_Blob":
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _take(blob: "_Blob") -> bytes:
        out = ctypes.string_at(blob.pbData, blob.cbData)
        ctypes.windll.kernel32.LocalFree(blob.pbData)
        return out


def _mac_keychain_set(password: str) -> bool:
    try:
        subprocess.run(
            ["security", "add-generic-password", "-U",
             "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w", password],
            check=True, capture_output=True,
        )
        return True
    except Exception:
        return False


def _mac_keychain_get() -> str:
    try:
        done = subprocess.run(
            ["security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
            check=True, capture_output=True, text=True,
        )
        return done.stdout.strip()
    except Exception:
        return ""


def encrypt(text: str) -> str:
    """평문 → 설정 파일에 저장할 토큰. 저장할 수 없는 환경이면 빈 문자열."""
    if not text:
        return ""
    if IS_WINDOWS:
        src, dst = _blob(text.encode("utf-8")), _Blob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dst)
        )
        return base64.b64encode(_take(dst)).decode("ascii") if ok else ""
    if IS_MAC:
        return KEYCHAIN_TOKEN if _mac_keychain_set(text) else ""
    return ""  # 리눅스 등 — 저장하지 않는다


def decrypt(token: str) -> str:
    """토큰 → 평문. 못 풀면 빈 문자열."""
    if not token:
        return ""
    if token == KEYCHAIN_TOKEN:
        return _mac_keychain_get() if IS_MAC else ""
    if not IS_WINDOWS:
        return ""
    try:
        src, dst = _blob(base64.b64decode(token)), _Blob()
    except Exception:
        return ""
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dst)
    )
    return _take(dst).decode("utf-8", errors="replace") if ok else ""


def _blank() -> dict:
    return {"mall_url": DEFAULT_MALL_URL, "login": {"id": "", "password": ""}}


def load(path: str | Path) -> dict:
    """설정을 읽어 비밀번호를 평문으로 풀어 돌려준다.

    🚨 **절대 예외를 던지지 않는다.** 설정 파일이 한 글자라도 깨지면
       [설정]도 [발주 시작]도 아무 반응 없는 앱이 되어버린다. `--windowed` exe는
       콘솔이 없고 Tk가 콜백 예외를 삼켜서, 사장님에게는 오류창조차 안 뜬다.
       깨진 파일은 `config.json.bad`로 밀어두고 빈 설정으로 시작한다.
    """
    path = Path(path)
    if not path.exists():
        return _blank()

    try:
        # utf-8-sig: 메모장이나 PowerShell이 붙이는 BOM을 흡수한다
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict):
            raise ValueError("설정 형식이 올바르지 않습니다")
    except Exception:
        _quarantine(path)
        return _blank()

    login = config.setdefault("login", {})
    if not isinstance(login, dict):
        login = config["login"] = {}
    # 암호화본이 있으면 그걸 쓰고, 없으면 예전 평문 키를 그대로 받아준다.
    if login.get("password_enc"):
        login["password"] = decrypt(login["password_enc"])
    config.setdefault("mall_url", DEFAULT_MALL_URL)
    return config


def _quarantine(path: Path) -> None:
    """깨진 설정을 옆으로 치운다. 지우지는 않는다 — 원인 파악에 쓸 수 있다."""
    try:
        path.replace(path.with_suffix(path.suffix + ".bad"))
    except Exception:
        try:
            path.unlink()
        except Exception:
            pass


def save(path: str | Path, config: dict) -> bool:
    """비밀번호를 암호화해 저장한다. 성공 여부를 돌려준다.

    임시 파일에 쓰고 바꿔치기한다 — 저장 도중 앱이 죽어도 **잘린 설정 파일이 남지 않는다.**
    """
    path = Path(path)
    stored = json.loads(json.dumps(config))  # 원본을 건드리지 않는다
    login = stored.setdefault("login", {})
    password = login.pop("password", "")

    encrypted = encrypt(password) if password else ""
    if encrypted:
        login["password_enc"] = encrypted
    else:
        # DPAPI가 실패하는 환경이면 저장하지 않는다 — 평문으로 남기느니 매번 입력받는다.
        login.pop("password_enc", None)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    except Exception:
        return False

    return bool(encrypted) or not password


def is_complete(config: dict) -> bool:
    login = config.get("login", {})
    return bool(config.get("mall_url") and login.get("id") and login.get("password"))
