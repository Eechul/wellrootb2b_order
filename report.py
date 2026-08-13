"""라인별 결과 리포트.

부분 성공을 조용히 넘기지 않는 게 이 모듈의 존재 이유다.
일부 라인이 실패했는데 나머지로 주문이 나가면 "일부만 주문된 상태"가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    OK = "성공"
    SOLD_OUT = "품절"
    OPTION_MISMATCH = "옵션 확인 필요"
    PAGE_ERROR = "상품 확인 필요"
    FAILED = "실패"


@dataclass
class LineResult:
    row: int
    product_url: str
    status: Status
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


class Report:
    def __init__(self, log=print) -> None:
        self.results: list[LineResult] = []
        self._log = log  # CLI는 print, GUI는 로그창으로 보낸다

    def add(self, row: int, product_url: str, status: Status, detail: str = "") -> None:
        self.results.append(LineResult(row, product_url, status, detail))
        mark = "✓" if status is Status.OK else "✗"
        suffix = f" — {detail}" if detail else ""
        self._log(f"   {mark} {row}행 {status.value}{suffix}")

    @property
    def failures(self) -> list[LineResult]:
        return [r for r in self.results if not r.ok]

    def summary(self) -> str:
        total = len(self.results)
        failed = self.failures
        ok = total - len(failed)

        lines = ["", "=" * 56, f"결과: {total}건 중 {ok}건 담김, {len(failed)}건 실패"]

        if failed:
            lines.append("")
            lines.append("⚠ 아래 상품은 장바구니에 담기지 않았습니다:")
            for r in failed:
                detail = f" ({r.detail})" if r.detail else ""
                lines.append(f"    {r.row}행 [{r.status.value}]{detail} {r.product_url}")
            lines.append("")
            lines.append("  이대로 결제하면 위 상품은 빠진 채 주문됩니다.")
            lines.append("  장바구니를 직접 확인한 뒤 결제하세요.")

        lines.append("=" * 56)
        return "\n".join(lines)
