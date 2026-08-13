"""실행 이력 — 중복 발주를 막고, 중간에 끊긴 발주를 이어서 할 수 있게 한다.

같은 엑셀을 두 번 돌려 같은 주문이 두 번 나가는 게 이 도메인 최악의 사고다.
그래서 **결제까지 확인된 주문**을 기록해두고, 재실행 시 그 배송지는 건너뛴다.
결과적으로 "중간에 끊긴 발주 이어하기"도 같은 엑셀을 다시 돌리기만 하면 된다.

기록 파일은 `history.jsonl`(추가 전용). 수령인·주소가 들어가므로 커밋하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
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
        self.broken_lines = 0  # 읽지 못한 줄 수 — 조용히 넘기지 않고 알린다
        self.unreadable = False  # 파일 자체를 못 읽었다
        self._load()

    def _load(self) -> None:
        """🚨 이력 때문에 발주가 막히면 안 된다. 어떤 손상이든 읽을 수 있는 만큼만 읽는다.

        다만 **조용히 넘기지도 않는다.** 손상된 줄이 '결제 확인'이었다면
        이미 결제한 주문을 다시 결제하게 되므로, 몇 줄을 못 읽었는지 알려야 한다.
        """
        if not self.path.exists():
            return
        try:
            # errors="replace": 정전·강제종료로 깨진 바이트가 있어도 읽기는 성공시킨다
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            self.unreadable = True
            return

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                self.broken_lines += 1
                continue
            if not isinstance(entry, dict):
                self.broken_lines += 1
                continue
            if entry.get("status") == STATUS_PAID:
                self._paid.add((entry.get("excel", ""), entry.get("group", "")))

    @property
    def paid_count(self) -> int:
        return len(self._paid)

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
        # flush+fsync: 정전이나 강제 종료로 줄이 반만 쓰이는 걸 줄인다.
        # 이 파일이 깨지면 이미 결제한 주문을 다시 결제할 수 있다.
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if status == STATUS_PAID:
            self._paid.add((excel_hash, group_key))


def group_key(group) -> str:
    """배송지 식별자. 같은 수취인·연락처·주소면 같은 주문으로 본다."""
    return "|".join(group.lines[0].shipping_key) if group.lines else ""
