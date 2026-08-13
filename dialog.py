"""브라우저 alert/confirm 처리.

이 몰은 장바구니 담기에서 confirm을 띄운다("장바구니에 동일한 상품이 있습니다...").
자동으로 수락하되 **메시지를 남겨둔다** — 담기가 실패했을 때 그 이유가 여기 들어 있기 때문이다.

전부 수락해도 안전한 이유: 이 도구는 결제하기(#btn_payment)를 절대 누르지 않는다.
"""

from __future__ import annotations

from playwright.sync_api import Page


class DialogLog:
    def __init__(self, page: Page) -> None:
        self.messages: list[str] = []
        page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog) -> None:
        self.messages.append(dialog.message.replace("\n", " ").strip())
        dialog.accept()

    def take(self) -> list[str]:
        """쌓인 메시지를 꺼내고 비운다."""
        messages = self.messages[:]
        self.messages.clear()
        return messages
