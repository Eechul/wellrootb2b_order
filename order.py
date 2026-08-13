"""발주 엑셀을 읽어 웰루트 B2B몰 장바구니에 담고 주문서까지 채운다. 결제는 사람이 한다.

GUI는 app.py. 둘 다 runner.py의 같은 흐름을 쓴다.

    python order.py 발주.xlsx              # 실행 (브라우저를 띄운다)
    python order.py 발주.xlsx --dry-run    # 엑셀 검증만. 브라우저를 띄우지 않는다
    python order.py 발주.xlsx --clear-cart # 기존 장바구니를 비우고 시작
    python order.py --template             # 발주 엑셀 템플릿 생성
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import credentials
from excel_reader import ExcelError, OrderGroup, read_orders

from storage import APP_DIR, CONFIG_PATH, HISTORY_PATH, SESSION_PATH

ROOT = Path(__file__).parent  # 템플릿 저장 등 프로젝트 파일용


def main() -> int:
    parser = argparse.ArgumentParser(description="웰루트 B2B몰 소량 발주 자동화")
    parser.add_argument("excel", nargs="?", help="발주 엑셀 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="엑셀 검증만 하고 브라우저를 띄우지 않음")
    parser.add_argument("--clear-cart", action="store_true", help="기존 장바구니를 비우고 시작")
    parser.add_argument("--headless", action="store_true", help="브라우저 창을 띄우지 않음 (테스트용)")
    parser.add_argument("--force", action="store_true", help="이미 결제된 이력이 있는 배송지도 다시 주문")
    parser.add_argument("--template", action="store_true", help="발주 엑셀 템플릿을 만들고 종료")
    args = parser.parse_args()

    if args.template:
        return make_template()

    if not args.excel:
        parser.print_help()
        return 1

    try:
        groups = read_orders(args.excel)
    except ExcelError as e:
        print(f"\n❌ {e}\n")
        return 1
    except FileNotFoundError:
        print(f"\n❌ 파일을 찾을 수 없습니다: {args.excel}\n")
        return 1

    print_plan(groups)

    if args.dry_run:
        print("\n--dry-run 이므로 여기서 멈춥니다. 엑셀은 이상 없습니다.\n")
        return 0

    config = credentials.load(CONFIG_PATH)
    if not credentials.is_complete(config):
        print(
            f"\n❌ 계정 설정이 없습니다: {CONFIG_PATH}\n"
            "   app.py의 [설정]에서 입력하거나, config.example.json을 복사해 채우세요.\n"
        )
        return 1

    import runner

    result = runner.run_orders(
        groups,
        args.excel,
        config,
        log=print,
        ask_payment=_ask_payment,
        history_path=HISTORY_PATH,
        session_path=SESSION_PATH,
        clear_cart=args.clear_cart,
        force=args.force,
        headless=args.headless,
    )

    print(result.report.summary())
    print(f"준비 {result.prepared}건 / 결제 확인 {result.paid}건 / 건너뜀 {result.skipped}건")
    if result.error:
        print(f"\n❌ {result.error}\n")
        return 1
    return 0 if result.ok else 1


def print_plan(groups: list[OrderGroup]) -> None:
    total = sum(len(g.lines) for g in groups)
    print(f"\n발주 라인 {total}건 → 배송지 {len(groups)}곳 = **주문 {len(groups)}건**")
    if len(groups) > 1:
        print("  (주문 1건에 배송지는 1곳이라 배송지 수만큼 나눠서 주문합니다)")
    for i, group in enumerate(groups, start=1):
        contact = group.tel + (f" / 휴대폰 {group.phone}" if group.phone else "")
        print(f"\n[{i}] {group.receiver} ({contact})")
        print(f"    {group.zipcode} {group.address} {group.address_detail}".rstrip())
        for line in group.lines:
            option = f" [{line.option}]" if line.option else ""
            product = f"상품 {line.product_no}" if line.product_no else line.product_url
            print(f"    · {line.row}행  {product}{option}  ×{line.quantity}")


def _ask_payment(index: int, total: int) -> str:
    if index >= total:
        prompt = "     결제가 끝나면 Enter를 눌러 브라우저를 닫습니다... "
    else:
        prompt = f"     결제 후 Enter (다음 주문 {index + 1}/{total}로) / q + Enter (중단): "
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        print("\n     (자동 실행이라 결제 대기를 건너뜁니다)")
        return "next"
    return "quit" if answer == "q" else "next"


def make_template() -> int:
    import template

    path = template.write_template(ROOT / template.DEFAULT_NAME)
    print(f"\n✅ 양식을 만들었습니다: {path}\n")
    print(template.HELP_TEXT)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
