"""실행 이력 — 중복 발주를 막고, 중간에 끊긴 발주를 이어서 할 수 있게 한다.

같은 엑셀을 두 번 돌려 같은 주문이 두 번 나가는 게 이 도메인 최악의 사고다.
그래서 **결제까지 확인된 주문**을 기록해두고, 재실행 시 그 배송지는 건너뛴다.
결과적으로 "중간에 끊긴 발주 이어하기"도 같은 엑셀을 다시 돌리기만 하면 된다.

기록 파일은 `history.jsonl`(추가 전용). 수령인·주소가 들어가므로 커밋하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

STATUS_PREPARED = "prepared"  # 결제 직전까지 채웠지만 결제는 확인 안 됨
STATUS_PAID = "paid"  # 결제 후 장바구니가 비어 결제가 확인됨


def excel_fingerprint(path: str | Path) -> str:
    """(구버전) 파일 바이트 기준 지문. 호환을 위해 남겨둔다.

    ⚠ 이걸 쓰면 안 된다 — 엑셀을 **열었다 저장만 해도** 바이트가 바뀌어
      이미 결제한 배송지를 못 알아본다. `order_fingerprint`를 쓸 것.
    """
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]


def order_fingerprint(groups) -> str:
    """발주 **내용** 기준 지문.

    엑셀을 다시 저장하거나 파일명을 바꿔도, 다른 줄의 오타를 고쳐도
    이 발주가 같은 발주임을 알아본다. 배송지·상품·수량만 본다.

    (파일 바이트로 잡으면 엑셀을 한 번 열었다 저장하는 것만으로
     중복 발주 방지가 통째로 풀린다 — 실사용에서 아주 흔한 시나리오다.)
    """
    parts = []
    for group in groups:
        items = sorted(
            f"{line.product_no or line.product_url}|{line.option}|{line.quantity}"
            for line in group.lines
        )
        parts.append("|".join(group.lines[0].shipping_key) + "»" + ",".join(items))
    payload = "\n".join(sorted(parts))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class History:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._paid: set[tuple[str, str]] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # 손상된 줄은 무시한다 — 이력 때문에 발주가 막히면 안 된다
            if entry.get("status") == STATUS_PAID:
                self._paid.add((entry.get("excel", ""), entry.get("group", "")))

    def is_paid(self, excel_hash: str, group_key: str) -> bool:
        return (excel_hash, group_key) in self._paid

    def record(
        self,
        excel_hash: str,
        excel_name: str,
        group_key: str,
        receiver: str,
        rows: list[int],
        status: str,
    ) -> None:
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "excel": excel_hash,
            "file": excel_name,
            "group": group_key,
            "receiver": receiver,
            "rows": rows,
            "status": status,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if status == STATUS_PAID:
            self._paid.add((excel_hash, group_key))


def group_key(group) -> str:
    """배송지 식별자. 같은 수취인·연락처·주소면 같은 주문으로 본다."""
    return "|".join(group.lines[0].shipping_key) if group.lines else ""
