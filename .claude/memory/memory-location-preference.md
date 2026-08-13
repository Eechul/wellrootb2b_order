---
name: memory-location-preference
description: 사용자는 이 프로젝트의 메모리와 CLAUDE.md를 프로젝트 폴더 안에 기록하길 원함
metadata:
  type: feedback
---

사용자 지시(2026-08-12): "지금 이 세션의 폴더 경로야. 한 프로젝트라고 봐도 되니 여기에 메모리 기록하고 claude.md도 기록하길 바란다."

**적용 방법:** 기본 홈 경로(`~/.claude/projects/.../memory/`)가 아니라
**`c:\Users\MSI\Desktop\0_github_프로그램\wellrootb2b_order\.claude\memory\`** 에 `<slug>.md`로 쓰고,
인덱스 `MEMORY.md`도 같은 폴더에서 관리한다. `CLAUDE.md`는 프로젝트 루트에 둔다.

**Why:** 메모리를 저장소 안에 두어 버전 관리·가시성을 확보하고 여러 PC에서 세션을 이어가려는 의도.
동일한 지시를 `dongsoft-cpn`, `kh_balju_server`에도 이미 적용해 둔 사용자의 일관된 작업 방식이다.

**How to apply:** 기본 메모리 시스템은 홈 경로를 보므로 이 폴더의 메모리는 자동 로드되지 않을 수 있다.
세션 시작 시 `CLAUDE.md`의 메모리 표를 따라 직접 읽을 것. 홈 경로에는 여기를 가리키는 포인터만 둔다.
