---
name: cafe24-api-constraints
description: 카페24 공식 문서로 검증한 API 제약 — 일반 주문생성 API 부재, 토큰 2시간/2주, leaky bucket rate limit
metadata:
  type: reference
---

2026-08-12에 [카페24 Admin API 문서](https://developers.cafe24.com/docs/api/admin/)를 직접 확인해 검증한 사실.
추측이 아니라 문서 기준이므로, 설계 판단의 근거로 그대로 써도 된다.

## 1. 일반 주문 생성 API가 없다 (핵심)

존재하는 주문 엔드포인트:
- `GET /api/v2/admin/orders`, `GET /api/v2/admin/orders/{order_no}`
- `PUT /api/v2/admin/orders`, `PUT /api/v2/admin/orders/{order_no}` (상태 변경)
- `GET|POST|PUT|DELETE /api/v2/admin/orders/migrations` ← **주문 생성용 POST는 이것뿐**

`POST /api/v2/admin/orders`는 **없다.** 임대형 쇼핑몰이 자체 PG 수수료와 결제 표준화를 지키려는 구조적 선택이라
앞으로 열릴 가능성도 낮다고 보는 게 안전하다.

`orders/migrations`는 원래 **타 솔루션에서 카페24로 이전할 때 과거 주문을 DB에 밀어 넣는 용도**다.
이를 B2B 발주 투입에 응용하는 건 실무에서 쓰이는 workaround지 정식 용법이 아니다 →
정상 장바구니/결제 로직을 안 타므로 **쿠폰·회원등급 할인 자동적용 없음, 알림톡·외부 WMS 트리거 미작동 가능**.
최종 결제금액은 우리 서버가 계산해서 넘겨야 한다.

## 2. 토큰 수명 — 운영 리스크 1순위

- **access token: 2시간**
- **refresh token: 2주** (갱신하면 둘 다 재발급되고 이전 refresh token은 무효)
- 토큰 발급 요청은 **2시간에 최대 15회**, 몰당 동시 발급 토큰 15개 초과 시 오래된 것부터 폐기

→ **2주 동안 갱신에 한 번도 성공 못 하면 몰 관리자가 직접 재인증**해야 한다.
무인 중계 서버에서 이건 곧 서비스 정지다. 자동 갱신 스케줄러 + 실패 즉시 알림이 필수이고,
토큰은 프로세스 메모리가 아니라 **영속 저장소에 두고 단일 갱신 주체**가 관리해야 한다(경쟁 갱신 시 서로 무효화됨).

## 3. Rate limit

- **Leaky bucket**: 몰별 버킷 용량이 있고 초과하면 429. 버킷은 **초당 2건씩** 배출.
- **동일 IP는 몰당 초당 10회** 초과 시 비정상 트래픽으로 분류될 수 있음.
- 응답 헤더로 사용량 추적 가능: `X-Cafe24-Call-Usage` / `X-Cafe24-Call-Remain`,
  `X-Cafe24-Time-Usage` / `X-Cafe24-Time-Remain`. 100% 도달 시 일시 차단.

→ 대량 발주(수백 라인)를 동기 루프로 때리면 바로 막힌다. **큐 + 지수 백오프 + 헤더 기반 셀프 스로틀링** 전제로 설계할 것.

## 4. 예치금은 API로 차감할 수 없다 (이 프로젝트의 결정적 제약)

이 몰은 **예치금 결제 위주**다(2026-08-12 확인). 그런데 문서 인덱스를 세 번 독립적으로 조회한 결과:

| 리소스 | 엔드포인트 | 잔액 증감 |
|---|---|---|
| 적립금(Points) | `GET /api/v2/admin/points`, **`POST /api/v2/admin/points`** ("Issue and deduct points") | **가능** |
| 예치금(Credits) | `GET /api/v2/admin/credits` (기간별 조회), `GET /api/v2/admin/credits/report` | **조회만 — 증감 API 없음** |

→ **`orders/migrations`로 주문을 밀어 넣어도 회원 예치금이 차감되지 않고, API로 수동 차감할 방법도 없다.**
예치금 몰에서 잔액 불일치는 곧 돈 문제라 이건 우회가 아니라 차단 조건이다. → [[architecture-decisions]]

*확신도: 높음(3회 독립 조회에서 동일). 다만 문서 인덱스 요약 기반이라 개발자센터에 최종 확인 권장 → [[open-questions]]*

## 5. Front API(장바구니)의 인증 형태

- 인증은 **HTTP Basic** — `base64(client_id:front_api_key)`. 필요 scope는 `mall.write_personal`(개인화정보 쓰기).
- **단, 장바구니는 회원 로그인 세션에 귀속된다는 자료가 있다.** 사실이면 서버-투-서버 호출이 아니라
  **사장님 브라우저(로그인 상태)에서 호출**하는 형태여야 한다. 이게 B 경로의 구현 형태를 결정하므로
  **직접 검증 필요 1순위** → [[open-questions]]

## 6. 기타

- 일부 API는 **특정 클라이언트만 사용 가능**("해당 API는 특정 클라이언트만 사용할 수 있는 API입니다").
  예: `GET /api/v2/admin/activitylogs`. `orders/migrations`도 별도 승인이 필요한지 **개발자센터 확인 필요** → [[open-questions]]
