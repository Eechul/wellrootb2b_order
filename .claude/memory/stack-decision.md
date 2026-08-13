---
name: stack-decision
description: MVP 스택 = Python + Playwright, CLI 먼저. 자동화는 주문서 입력까지만 하고 결제 클릭은 사람이
metadata:
  type: project
---

사용자 결정(2026-08-12).

## 스택: Python + Playwright, CLI 우선

GUI 없이 CLI로 먼저 만들고, 동작이 안정되면 그때 Tkinter/Electron을 씌운다.

**Playwright를 고른 이유:**
- **auto-wait** — 카페24 스킨의 느린 로딩에서 `element not found`가 급감한다. Selenium은 명시적 대기를 직접 짜야 한다.
- **`playwright codegen`** — 실제 주문 흐름을 브라우저에서 한 번 클릭하면 셀렉터가 자동 생성된다.
  이 프로젝트 작업량의 절반이 셀렉터 찾기라 이 이점이 가장 크다. **막히면 항상 codegen부터 돌릴 것.**
- 세션(스토리지 상태) 저장이 기본 제공 → 로그인 반복을 줄여 캡차 위험도 낮춘다.

기존 자산인 `cpotalecnt_order_pj`(Electron+Selenium) 구조는 참고만 하고 복제하지 않는다.
단, 그 프로젝트의 **배송지별 그룹핑** 아이디어는 그대로 가져왔다.

## 정지 지점: 주문서 입력까지

장바구니 담기 + 수취인·주소·연락처 자동 입력까지 하고 **결제 화면에서 멈춘다.**
사람이 눈으로 확인한 뒤 결제를 클릭한다.

**Why:** 예치금이 잘못 빠지면 되돌리는 게 주문 취소 처리라 비용이 크다.
반복작업의 90%는 이 지점까지로 이미 사라지고, 남은 10%(클릭 한 번)가 안전장치 역할을 한다.
자동화가 신뢰를 얻은 뒤에 마지막 클릭을 넘기는 순서로 간다. → [[mvp-browser-automation]]
