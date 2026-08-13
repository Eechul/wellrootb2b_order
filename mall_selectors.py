"""wellrootb2b.com 셀렉터 — **여기에만** 둔다.

⚠ 파일 이름을 `selectors.py`로 되돌리지 말 것 — 파이썬 표준 모듈 `selectors`를 가려서
  asyncio·socketserver 같은 표준 라이브러리가 조용히 깨진다(실제로 겪음).

몰 스킨이 바뀌면 깨지는 건 이 파일 하나뿐이어야 한다. 다른 파일에 셀렉터 문자열을 쓰지 말 것.
아래 값은 2026-08-12에 실제 사이트에 로그인해 DOM을 확인하고 채운 것이다.

깨졌을 때: `playwright codegen https://wellrootb2b.com` 로 실제 화면을 클릭하면 셀렉터가 나온다.
"""


class Login:
    """/member/login.html"""

    URL_PATH = "/member/login.html"
    ID_INPUT = "#member_id"
    PASSWORD_INPUT = "#member_passwd"
    # 로그인 성공 판정 — 로그인 후에만 존재한다. 가장 확실한 신호.
    LOGGED_IN_MARKER = 'a[href="/exec/front/Member/logout/"]'
    # 헤더에 보유 예치금이 노출된다. 발주 전 잔액 확인에 쓴다.
    DEPOSIT_BALANCE = 'a[href="/myshop/deposits/historyList.html"]'


class Product:
    """/product/detail.html?product_no=N"""

    QUANTITY_INPUT = "#quantity"  # name="quantity_opt[]"

    # 본품 옵션. 이 몰에서 아직 실물을 못 봤다 — 있는 상품을 만나면 검증할 것.
    OPTION_SELECTS = 'select[id^="product_option_id_"]'
    # 추가상품(스푼 등). 본품 옵션과 별개이고, [필수] 표기가 있어도 미선택으로 담기가 된다(실측).
    ADDPRODUCT_SELECTS = 'select[id^="addproduct_option_id_"]'

    # ⚠ 감싸고 있는 <a>는 display:inline이라 Playwright가 클릭 불가로 판단한다.
    #   반드시 안쪽 div를 클릭할 것. (실측으로 확인된 함정)
    ADD_TO_CART = ".basket_bt"  # <a onclick="product_submit(2, '/exec/front/order/basket/', this)">
    BUY_NOW = ".buy_bt"  # <a onclick="product_submit(1, ...)"> — 이 도구는 쓰지 않는다

    SOLD_OUT_MARKER = ".buy_bt:has-text('SOLD OUT')"
    PRODUCT_NAME = ".detailArea .headingArea h2, .detailArea h2"


class Cart:
    """/order/basket.html"""

    URL_PATH = "/order/basket.html"
    ITEM_CHECKBOX = 'input[id^="basket_chk_id_"]'
    # 🚨 "항목 0개"와 "장바구니 화면을 못 읽음"을 반드시 구분해야 한다.
    #   결제 여부를 '장바구니가 비었나'로 판정하기 때문에, 화면을 못 읽은 걸 0으로 세면
    #   결제 안 한 주문이 '결제 완료'로 기록되고 그 배송지는 영영 누락된다.
    # 따옴표 없는 text= 는 **부분 일치**다. 실제 문구가 "장바구니가 비어 있습니다." 처럼
    # 마침표를 달고 나오므로 정확 일치(따옴표)로 잡으면 매칭되지 않는다.
    EMPTY_MARKER = "text=장바구니가 비어 있습니다"
    ORDER_ALL = 'a[onclick*="Basket.orderAll"]'  # 전체상품주문
    DELETE_SELECTED = 'a[onclick*="Basket.deleteBasket()"]'  # 삭제하기


class OrderForm:
    """/order/orderform.html"""

    URL_MARKER = "/order/orderform.html"

    # 배송지: 주문자와 동일(T) / 새로 입력(F)
    SHIPPING_SAME = "#sameaddr0"
    SHIPPING_NEW = "#sameaddr1"

    RECEIVER = "#rname"
    ZIPCODE = "#rzipcode1"
    ADDRESS = "#raddr1"
    ADDRESS_DETAIL = "#raddr2"
    # 연락처는 3칸으로 쪼개져 있다. 1은 select(지역/통신사), 2·3은 text.
    PHONE_PARTS = ("#rphone2_1", "#rphone2_2", "#rphone2_3")  # 휴대전화
    TEL_PARTS = ("#rphone1_1", "#rphone1_2", "#rphone1_3")  # 일반전화

    # 예치금 — 이 몰은 예치금으로만 결제한다
    # ("예치금 구매를 제외한 모든 제품은 예치금으로만 결제 가능합니다")
    DEPOSIT_INPUT = "#input_deposit"
    DEPOSIT_USE_ALL = "#all_use_deposit"  # 스킨이 텍스트를 '사용'으로 바꿔놓은 그 버튼
    DEPOSIT_BALANCE_TEXT = ".summary .txtEm"
    # 결제하기 버튼 안에 최종 결제금액이 들어 있다. 예치금 부족 판정에 쓴다.
    TOTAL_PRICE = "#total_order_sale_price_view"

    # ⛔ 결제하기(#btn_payment)는 일부러 두지 않는다.
    #    MVP는 여기서 사람에게 넘긴다 — .claude/memory/mvp-browser-automation.md 설계 원칙.
    #    누군가 자동 결제를 추가하려 하면 그 메모리를 먼저 읽을 것.
