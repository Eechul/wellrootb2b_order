---
name: distribution
description: 거래처 사장님들께 exe로 배포 — 브라우저는 설치된 Chrome/Edge, 업데이트는 GitHub Releases 권장
metadata:
  type: project
---

사용자 결정(2026-08-12): **거래처 사장님들께 배포**한다. GUI는 Tkinter. → [[stack-decision]]

## 브라우저를 exe에 넣지 않는다

`browser.py`가 **설치된 Chrome → Edge → 내장 크로미움** 순으로 실행한다.
실측으로 Chrome(151), Edge(151) 둘 다 Playwright `channel=`로 잘 붙는다.
**Edge는 윈도우 기본 탑재**라 어느 PC에서든 폴백이 있다 — 이게 이 방식을 안전하게 만든다.

## exe 크기: 약 60MB (압축 후)

브라우저를 빼도 **Playwright의 Node 드라이버(`driver/node.exe` 86MB)는 반드시 들어간다.**
playwright 패키지 전체가 약 114MB(driver 98 + 나머지 16). 여기에 파이썬 런타임이 붙는다.
처음에 30MB로 잡았던 건 이 드라이버를 빠뜨린 오산이었다.

→ **구글 드라이브가 애매해지는 지점.** 100MB를 넘으면 바이러스 검사 확인 페이지가 끼어들어
   직접 다운로드가 깨진다. 60MB면 지금은 통과하지만 여유가 없다.

## 업데이트 배포처: GitHub Releases 권장

| 방식 | 판단 |
|---|---|
| **GitHub Releases** | 권장. 직링크 안정적, 자산 2GB까지, 버전별 보관, 무료. **단 public 저장소여야 한다**(private은 토큰 필요 → 배포 불가) |
| 구글 드라이브 | 가능은 함. `uc?export=download&id=...`, 파일은 '새 버전 관리'로 덮어써야 ID가 유지된다. 100MB 근접·인기 파일 할당량이 위험 |
| 몰/자체 서버 | 운영자 협조가 되면 가장 자연스럽다 |

소스를 공개하기 싫으면 **릴리스 전용 public 저장소**를 따로 만들면 된다(코드 없이 자산만 올림).

`updater.py`는 URL만 보므로 **어느 쪽을 골라도 코드 변경이 없다** — `config.json`의 `update_url`만 바꾼다.

## 자기 자신을 교체하는 방법

윈도우는 실행 중인 exe를 덮어쓸 수 없다. 그래서:
새 파일을 임시폴더에 받고 → 배치 파일을 띄우고 → 앱은 종료 →
배치가 PID 소멸을 기다렸다가 교체하고 다시 실행한다. (`updater.py`의 `apply_and_restart`)

- **exe를 `Program Files`에 두면 교체에 관리자 권한이 필요하다.** 바탕화면/사용자 폴더 전제.
- **exe 이름은 ASCII로.** 한글 이름은 배치·URL에서 인코딩 문제를 만든다. `WellrootOrder.exe`로 고정.
- 실패하면 백업(`.exe.old`)을 되돌린다.

## 비밀번호 보관

윈도우 **DPAPI**(`CryptProtectData`)로 암호화해 `config.json`에 `password_enc`로 넣는다.
ctypes로 OS 기능을 직접 부르므로 **추가 패키지가 없다**(PyInstaller에 유리).
윈도우 사용자 계정에 묶이므로 **설정 파일을 다른 PC로 복사해도 안 풀린다.**
DPAPI가 실패하는 환경이면 아예 저장하지 않는다 — 평문으로 남기느니 매번 입력받는 쪽이 낫다.

## 맥 지원 (2026-08-12 확인)

**본체 코드는 이미 크로스플랫폼이다.** Playwright·Tkinter·openpyxl·엑셀 파싱·주문 흐름 전부 그대로 돈다.
`channel="chrome"`도 맥에서 동작한다. OS 의존은 **딱 두 곳**뿐이었고 둘 다 분기 처리해 뒀다:

| 부분 | 윈도우 | 맥 | 그 외 |
|---|---|---|---|
| 비밀번호 보관 | DPAPI | **키체인**(`security` 명령) | 저장 안 함(매번 입력) |
| 자동 교체 | .bat + tasklist | **미구현** — 안내 후 수동 교체 | 동일 |

업데이트 **확인·다운로드**는 어느 OS에서나 되고, 자기 교체만 윈도우 전용이다.

**막히는 건 코드가 아니라 배포다:**
- PyInstaller는 **크로스 컴파일이 안 된다.** 맥 앱을 만들려면 맥에서 빌드해야 한다.
- 서명 없는 앱은 Gatekeeper가 막는다("확인되지 않은 개발자"). 사장님들께 우클릭→열기를 안내하거나
  **Apple Developer Program(연 $99)** 으로 공증(notarize)해야 한다. 이게 실질 비용이다.
- 맥에서 Homebrew 파이썬을 쓰면 `python-tk`를 따로 깔아야 Tkinter가 있다.

→ **수요를 먼저 확인할 것.** 도매 사장님들은 대개 윈도우다. 실제로 맥 쓰는 분이 있을 때 붙이는 게 맞다.

## 빌드 실측 (2026-08-12)

`.\build.ps1` → **48.3MB / GUI 기동 2.6초 / 메모리 53MB.** 자가진단 통과.

```
python app.py --selftest      # 또는 WellrootOrder.exe --selftest
→ selftest.log: playwright 임포트 / 브라우저 실행 / 페이지 로드 / 암호화 / 엑셀 컬럼
```

**배포 전에 반드시 `--selftest`를 돌릴 것.** onefile은 Playwright의 Node 드라이버 경로에서 깨지기 쉬운데,
`--windowed`라 콘솔이 없어서 그냥 실행하면 실패가 눈에 안 보인다.

## 빌드에서 겪은 함정 (전부 잡아뒀지만 원리는 알고 있을 것)

1. **`--exclude-module`을 안 주면 numpy 같은 게 딸려 온다.** 68.6MB → 48.3MB (30% 감소).
2. **onefile은 부모/자식 두 프로세스로 뜬다.** 창은 자식이 갖는다.
   - 부모 PID로 창을 찾으면 못 찾는다(살아있는데 없는 것처럼 보인다)
   - 부모만 죽이면 자식이 남아 **exe를 잠근다** → 다음 빌드가 실패
   - `build.ps1`이 빌드 전에 이름으로 싹 정리한다
3. **PowerShell의 `$ErrorActionPreference = "Stop"`은 외부 명령의 종료코드를 잡지 않는다.**
   PyInstaller가 실패했는데 이전 exe를 두고 "완료"라고 보고했다. `$LASTEXITCODE`를 직접 봐야 한다.
   (실제로 겪음 — 같은 sha256이 나와서 알아챘다)
4. **🚨 onefile에서 `__file__`은 매 실행마다 새로 만들어지는 임시 압축해제 폴더다.**
   거기에 `config.json`을 저장하면 종료와 함께 사라진다 → 설정이 매번 초기화된다.
   반드시 `Path(sys.executable).parent`(exe 옆)를 쓸 것. `app.py`의 `app_dir()`, `order.py`의 `ROOT`.
5. **`--windowed`는 시작 시 예외를 조용히 삼킨다.** 사장님 눈에는 "눌렀는데 아무 일 없음"으로 보인다.
   `main()`이 모든 예외를 잡아 `error.log`에 남기고 창으로 알린다.

## 배포처 확정: GitHub Releases (2026-08-12)

저장소: https://github.com/Eechul/wellrootb2b_order (public)
매니페스트: `https://github.com/Eechul/wellrootb2b_order/releases/latest/download/update.json`

`releases/latest/download/...` 는 **항상 최신 릴리스**로 연결된다. 앱에 박아둔 주소가 안 바뀌므로
새 릴리스를 올리기만 하면 구버전 앱이 알아서 찾아온다.

**릴리스 순서 (반드시 이 순서로):**
```powershell
# 1. 코드를 먼저 커밋·push  ← 안 하면 태그가 엉뚱한 커밋을 가리킨다
git push
# 2. 빌드
$env:WELLROOT_NOTES = "이번 변경 내용"
.\build.ps1
# 3. 릴리스 업로드 (dirty/미push 이면 스스로 거부한다)
.\release.ps1
```

`update.json`을 GitHub API 대신 쓰는 이유: **배포처를 바꿔도 코드가 그대로**고(구글 드라이브·자체 서버 가능),
API 호출 제한이 없고, sha256을 직접 통제할 수 있다.

## 🚨 자동 교체가 죽던 버그 (2026-08-12 실검증에서 발견)

**다운로드까지 성공하고 교체 스크립트도 만들어지는데, 앱이 종료되는 순간 스크립트가 함께 죽었다.**
결과적으로 앱만 사라지고 아무 일도 안 일어난다. 배포 후 터졌으면 사장님 PC에서 앱이 통째로 없어지는 사고.

원인은 **윈도우 Job Object**. `DETACHED_PROCESS`로 띄워도 부모가 속한 Job이 정리될 때 자식까지 죽는다.

| 방식 | 부모 종료 후 |
|---|---|
| `DETACHED_PROCESS \| NEW_PROCESS_GROUP` | ❌ 죽음 (기존) |
| `DETACHED \| BREAKAWAY` | ❌ 죽음 |
| **`CREATE_NO_WINDOW \| NEW_GROUP \| CREATE_BREAKAWAY_FROM_JOB`** | ✅ 살아남음 (채택) |
| WMI `Win32_Process.Create` | ✅ 살아남음 (폴백) |

**추가 안전장치:** 스크립트가 신호 파일(`.started`)을 만들 때까지 최대 6초 기다린 뒤에만 앱을 닫는다.
못 뜨면 앱을 유지한 채 사유를 안내한다 — **앱만 사라지는 상황을 원천 차단**한다.

**교훈: 자기 교체는 실제로 새 버전을 올려 끝까지 돌려보기 전엔 검증된 게 아니다.**
그리고 **수정본은 그 버전부터만 효과가 있다** — 깨진 버전을 이미 받은 사람은 수동 교체뿐이다.
그래서 v0.1.0·v0.1.1(깨진 로직)은 삭제했다.

**실측: 0.1.2 → 0.1.3 자동 업데이트 14.4초, 자동 재실행까지 확인.**
