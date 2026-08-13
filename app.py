"""웰루트 발주 도우미 — Tkinter GUI.

자동화는 별도 스레드에서 돌고, 화면은 큐로 받은 로그만 그린다.
CLI의 `input()`(결제 대기)이 여기서는 [결제했음] 버튼이 된다 — 흐름은 runner.py 하나를 공유한다.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

import credentials
import resources
from excel_reader import ExcelError, read_orders
from version import (APP_NAME, DEFAULT_UPDATE_URL, SUPPORT_HINT, SUPPORT_LABEL,
                     SUPPORT_URL, VERSION)

from storage import APP_DIR, CONFIG_PATH, ERROR_LOG, HISTORY_PATH, SELFTEST_LOG, SESSION_PATH


class OrderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("720x620")
        self.minsize(620, 520)

        self.excel_path = tk.StringVar()
        self.status = tk.StringVar(value="발주 엑셀을 선택하세요.")

        self._events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._pay_gate = threading.Event()
        self._pay_answer = "next"

        # 🚨 Tk는 버튼 콜백에서 난 예외를 삼키고 mainloop을 계속 돈다.
        #   --windowed exe는 콘솔이 없어 traceback이 어디에도 안 남는다 → 사장님에게는
        #   "버튼을 눌러도 아무 일이 없다"로만 보이고 담당자에게 보낼 단서가 0이 된다.
        self.report_callback_exception = self._on_callback_error

        self._apply_icon()
        self._build()
        self.after(100, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # 업데이트 확인은 앱 시작을 막지 않도록 백그라운드에서
        threading.Thread(target=self._check_update, daemon=True).start()

    # ---------------------------------------------------------------- 화면

    def _on_callback_error(self, exc_type, exc_value, exc_tb) -> None:
        """버튼 콜백에서 난 예외를 파일로 남기고 사람에게 알린다. 조용히 사라지지 않게."""
        import traceback

        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            ERROR_LOG.write_text(detail, encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror(
                APP_NAME,
                "문제가 생겨 작업을 마치지 못했습니다.\n\n"
                f"{exc_value}\n\n"
                f"아래 파일을 담당자에게 보내주세요:\n{ERROR_LOG}",
            )
        except Exception:
            pass

    def _apply_icon(self) -> None:
        """창 제목 왼쪽(그리고 작업표시줄) 아이콘. 파일이 없으면 기본 아이콘으로 둔다."""
        icon = resources.asset("app.ico")
        if not icon:
            return
        try:
            self.iconbitmap(default=str(icon))
        except Exception:
            pass  # 아이콘 때문에 앱이 못 뜨는 일은 없어야 한다

    def _build_contact(self, parent) -> None:
        """창 오른쪽 아래 [문의하기] — 카카오톡 오픈채팅으로 보낸다.

        기본 브라우저로 열기만 한다. 앱은 링크가 죽어도 영향받지 않는다.
        """
        ttk.Label(parent, text=SUPPORT_HINT, foreground="#888").pack(side="right", padx=(6, 0))

        link = tk.Label(
            parent, text=SUPPORT_LABEL, foreground="#1a64c0", cursor="hand2", borderwidth=0
        )
        link.pack(side="right")
        underline = font.Font(font=link.cget("font"))
        underline.configure(underline=True)
        plain = link.cget("font")

        link.bind("<Button-1>", lambda _e: self._open_support())
        link.bind("<Enter>", lambda _e: link.configure(font=underline))
        link.bind("<Leave>", lambda _e: link.configure(font=plain))

    def _open_support(self) -> None:
        try:
            webbrowser.open(SUPPORT_URL)
        except Exception:
            # 브라우저를 못 열면 주소라도 보여준다
            messagebox.showinfo(APP_NAME, f"아래 주소로 문의해주세요.\n\n{SUPPORT_URL}")

    def _build_footer(self, parent) -> None:
        """창 하단 이미지. `assets/footer.png`가 있을 때만 그린다."""
        banner = resources.asset("footer.png")
        if not banner:
            return
        try:
            # Tk 8.6은 PNG를 그대로 읽는다(Pillow 불필요). 대신 크기 조절이 안 되니
            # 넣어준 그림을 그대로 그린다 — 그래서 규격을 맞춰 받아야 한다.
            self._footer_image = tk.PhotoImage(file=str(banner))
        except Exception:
            return
        tk.Label(parent, image=self._footer_image, borderwidth=0).pack(pady=(0, 8))

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="발주 엑셀").pack(side="left")
        ttk.Entry(top, textvariable=self.excel_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(top, text="찾아보기", command=self._pick_excel).pack(side="left")

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        self.btn_check = ttk.Button(actions, text="확인만 보기", command=self._check_only)
        self.btn_check.pack(side="left")
        self.btn_start = ttk.Button(actions, text="발주 시작", command=self._start)
        self.btn_start.pack(side="left", padx=8)
        ttk.Button(actions, text="설정", command=self._open_settings).pack(side="right")
        # exe만 받은 사장님은 양식을 구할 데가 없다 — 앱 안에서 만들 수 있어야 한다
        ttk.Button(actions, text="발주 양식 만들기", command=self._make_template).pack(
            side="right", padx=8
        )

        box = ttk.LabelFrame(self, text="진행")
        box.pack(fill="both", expand=True, padx=12, pady=6)
        self.log_view = tk.Text(box, wrap="word", state="disabled", height=18)
        scroll = ttk.Scrollbar(box, command=self.log_view.yview)
        self.log_view.configure(yscrollcommand=scroll.set)
        self.log_view.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        self.pay_frame = ttk.LabelFrame(self, text="결제 대기")
        self.pay_label = ttk.Label(
            self.pay_frame, text="", wraplength=660, justify="left"
        )
        self.pay_label.pack(anchor="w", padx=10, pady=(8, 4))
        row = ttk.Frame(self.pay_frame)
        row.pack(anchor="w", padx=10, pady=(0, 10))
        self.btn_paid = ttk.Button(row, text="결제했음 — 다음으로", command=lambda: self._answer("next"))
        self.btn_paid.pack(side="left")
        ttk.Button(row, text="중단", command=lambda: self._answer("quit")).pack(side="left", padx=8)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Label(bottom, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True)
        self._build_contact(bottom)

        self._build_footer(self)

    def _log(self, message: str = "") -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", message + "\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    # ---------------------------------------------------------------- 동작

    def _pick_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="발주 엑셀 선택", filetypes=[("엑셀 파일", "*.xlsx"), ("모든 파일", "*.*")]
        )
        if path:
            self.excel_path.set(path)
            self.status.set("‘확인만 보기’로 배송지 묶음을 먼저 보세요.")

    def _make_template(self) -> None:
        """발주 양식을 만들어 저장하고, 바로 쓸 수 있게 파일 위치까지 열어준다."""
        import template

        target = filedialog.asksaveasfilename(
            title="발주 양식을 저장할 위치",
            initialfile=template.DEFAULT_NAME,
            initialdir=str(Path.home() / "Desktop"),
            defaultextension=".xlsx",
            filetypes=[("엑셀 파일", "*.xlsx")],
        )
        if not target:
            return

        try:
            saved = template.write_template(target)
        except PermissionError:
            messagebox.showerror(
                APP_NAME,
                "양식을 저장하지 못했습니다.\n\n"
                "같은 이름의 엑셀 파일이 열려 있으면 닫고 다시 시도해주세요.",
            )
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"양식을 저장하지 못했습니다.\n\n{e}")
            return

        self.excel_path.set(str(saved))
        self.status.set("양식을 채운 뒤 ‘확인만 보기’를 눌러주세요.")
        messagebox.showinfo(APP_NAME, f"{template.HELP_TEXT}\n\n저장 위치:\n{saved}")
        try:
            os.startfile(saved.parent)  # noqa: S606 — 사용자가 만든 파일의 폴더 열기
        except Exception:
            pass

    def _load_groups(self):
        path = self.excel_path.get().strip()
        if not path:
            messagebox.showwarning(APP_NAME, "발주 엑셀을 먼저 선택해주세요.")
            return None
        try:
            return read_orders(path)
        except ExcelError as e:
            messagebox.showerror("엑셀을 확인해주세요", str(e))
        except FileNotFoundError:
            messagebox.showerror(APP_NAME, f"파일을 찾을 수 없습니다:\n{path}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"엑셀을 읽지 못했습니다.\n{e}")
        return None

    def _check_only(self) -> None:
        groups = self._load_groups()
        if not groups:
            return
        self._clear_log()
        total = sum(len(g.lines) for g in groups)
        self._log(f"발주 라인 {total}건 → 배송지 {len(groups)}곳 = 주문 {len(groups)}건")
        for i, group in enumerate(groups, start=1):
            contact = group.tel + (f" / 휴대폰 {group.phone}" if group.phone else "")
            self._log("")
            self._log(f"[{i}] {group.receiver} ({contact})")
            self._log(f"    {group.zipcode} {group.address} {group.address_detail}".rstrip())
            for line in group.lines:
                option = f" [{line.option}]" if line.option else ""
                product = f"상품 {line.product_no}" if line.product_no else line.product_url
                self._log(f"    · {line.row}행  {product}{option}  ×{line.quantity}")
        self.status.set("엑셀은 이상 없습니다. 묶음이 맞으면 ‘발주 시작’.")

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        config = credentials.load(CONFIG_PATH)
        if not credentials.is_complete(config):
            messagebox.showinfo(APP_NAME, "먼저 [설정]에서 몰 아이디와 비밀번호를 입력해주세요.")
            self._open_settings()
            return

        groups = self._load_groups()
        if not groups:
            return

        if not messagebox.askokcancel(
            APP_NAME,
            f"배송지 {len(groups)}곳, 주문 {len(groups)}건을 준비합니다.\n\n"
            "결제는 브라우저에서 직접 누르셔야 합니다.\n계속할까요?",
        ):
            return

        self._clear_log()
        self._set_busy(True)
        self.status.set("진행 중...")
        self._worker = threading.Thread(
            target=self._run, args=(groups, self.excel_path.get(), config), daemon=True
        )
        self._worker.start()

    def _run(self, groups, excel_path, config) -> None:
        """워커 스레드. 화면을 직접 건드리지 않고 큐로만 알린다."""
        import runner

        try:
            result = runner.run_orders(
                groups,
                excel_path,
                config,
                log=lambda m="": self._events.put(("log", m)),
                ask_payment=self._ask_payment,
                ask_clear_cart=self._ask_clear_cart,
                history_path=HISTORY_PATH,
                session_path=SESSION_PATH,
            )
            self._events.put(("done", result))
        except Exception as e:  # noqa: BLE001
            self._events.put(("crash", f"{type(e).__name__}: {e}"))

    def _ask_payment(self, index: int, total: int, failures=()) -> str:
        """워커 스레드에서 호출된다. 사람이 버튼을 누를 때까지 여기서 멈춘다."""
        self._pay_gate.clear()
        lines = [f"{r.row}행 {r.status.value}" for r in failures]
        self._events.put(("payment", (index, total, lines)))
        self._pay_gate.wait()
        return self._pay_answer

    def _ask_clear_cart(self, count: int) -> bool:
        """워커 스레드에서 호출된다. 장바구니에 남은 걸 비울지 사람에게 묻는다.

        예전에는 여기서 그냥 멈추고 '몰에서 직접 비우고 다시 실행하세요'라고 했다.
        손품을 줄이려고 쓰는 도구인데 앱을 껐다 켜게 만들면 안 된다.
        """
        self._pay_gate.clear()
        self._events.put(("confirm_clear", count))
        self._pay_gate.wait()
        return self._pay_answer == "next"

    def _answer(self, answer: str) -> None:
        self._pay_answer = answer
        self.pay_frame.pack_forget()
        self.status.set("진행 중..." if answer == "next" else "중단하는 중...")
        self._pay_gate.set()

    # ---------------------------------------------------------------- 큐 처리

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "payment":
                    index, total, missing = payload
                    base = (
                        f"주문 {index}/{total} 준비가 끝났습니다.\n"
                        "브라우저 창에서 금액과 배송지를 확인하고 [결제하기]를 누른 뒤, "
                        "아래 버튼을 눌러주세요."
                    )
                    if missing:
                        # 🚨 빠진 상품은 결제 전에 눈에 띄어야 한다. 로그는 스크롤돼 안 본다.
                        self.pay_label.configure(
                            text=f"⚠ 이 주문에서 {len(missing)}건이 빠졌습니다 — "
                            + ", ".join(missing)
                            + "\n그대로 결제하면 빠진 채 주문됩니다.\n\n"
                            + base,
                            foreground="#c0392b",
                        )
                        self.btn_paid.configure(text="빠진 상품 확인했고 그래도 결제함")
                    else:
                        self.pay_label.configure(text=base, foreground="")
                        self.btn_paid.configure(text="결제했음 — 다음으로")
                    self.pay_frame.pack(fill="x", padx=12, pady=(0, 6))
                    self.status.set(f"주문 {index}/{total} — 결제를 기다리는 중")
                elif kind == "confirm_clear":
                    ok = messagebox.askokcancel(
                        APP_NAME,
                        f"쇼핑몰 장바구니에 이미 {payload}건이 담겨 있습니다.\n\n"
                        "이 상품들을 비우고 발주를 진행할까요?\n"
                        "(비운 상품은 주문되지 않습니다)",
                    )
                    self._pay_answer = "next" if ok else "quit"
                    self._pay_gate.set()
                elif kind == "done":
                    self._finish(payload)
                elif kind == "crash":
                    self._set_busy(False)
                    self.status.set("오류로 중단되었습니다.")
                    messagebox.showerror(APP_NAME, payload)
                elif kind == "status":
                    self.status.set(payload)
                elif kind == "update":
                    self._offer_update(payload)
                elif kind == "update_failed":
                    self._set_busy(False)
                    self.status.set("업데이트에 실패했습니다.")
                    messagebox.showwarning(APP_NAME, f"업데이트에 실패했습니다.\n{payload}")
                elif kind == "quit_for_update":
                    self.destroy()
                    return
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _finish(self, result) -> None:
        self._set_busy(False)
        self.pay_frame.pack_forget()
        self._log(result.report.summary())
        self._log(f"준비 {result.prepared}건 / 결제 확인 {result.paid}건 / 건너뜀 {result.skipped}건")

        if result.error:
            self.status.set("중단되었습니다.")
            messagebox.showwarning(APP_NAME, result.error)
        elif result.report.failures:
            self.status.set("일부 상품이 담기지 않았습니다. 로그를 확인하세요.")
        else:
            self.status.set(f"완료 — 결제 확인 {result.paid}건")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.btn_start.configure(state=state)
        self.btn_check.configure(state=state)

    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askokcancel(
                APP_NAME, "진행 중입니다. 창을 닫으면 브라우저도 함께 닫힙니다.\n정말 닫을까요?"
            ):
                return
            self._pay_answer = "quit"
            self._pay_gate.set()
        self.destroy()

    # ---------------------------------------------------------------- 업데이트

    def _check_update(self) -> None:
        """백그라운드에서 새 버전을 확인한다. 실패해도 앱 사용에는 지장이 없다."""
        import updater

        if not updater.is_frozen():
            return  # 개발 중에는 건드리지 않는다
        config = credentials.load(CONFIG_PATH)
        found = updater.check(config.get("update_url") or DEFAULT_UPDATE_URL)
        if found:
            self._events.put(("update", found))

    def _offer_update(self, found) -> None:
        import updater

        notes = f"\n\n{found.notes}" if found.notes else ""
        if not messagebox.askyesno(
            APP_NAME,
            f"새 버전 {found.version}이 있습니다. (현재 {VERSION}){notes}\n\n지금 업데이트할까요?",
        ):
            return

        self.status.set(f"업데이트 {found.version} 내려받는 중...")
        self._set_busy(True)

        def work():
            try:
                new_exe = updater.download(
                    found,
                    progress=lambda done, total: self._events.put(
                        ("status", f"업데이트 내려받는 중... {done * 100 // total}%")
                    ),
                )
                updater.apply_and_restart(new_exe)
                self._events.put(("quit_for_update", None))
            except Exception as e:  # noqa: BLE001
                self._events.put(("update_failed", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- 설정

    def _open_settings(self) -> None:
        SettingsDialog(self, CONFIG_PATH)


class SettingsDialog(tk.Toplevel):
    """몰 계정 설정. 비밀번호는 윈도우 계정에 묶어 암호화 저장한다."""

    def __init__(self, parent: tk.Tk, config_path: Path) -> None:
        super().__init__(parent)
        self.title("설정")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.config_path = config_path
        config = credentials.load(config_path)

        self.mall = tk.StringVar(value=config.get("mall_url", credentials.DEFAULT_MALL_URL))
        self.user_id = tk.StringVar(value=config["login"].get("id", ""))
        self.password = tk.StringVar(value=config["login"].get("password", ""))

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        for row, (label, var, hide) in enumerate(
            [("몰 주소", self.mall, False), ("아이디", self.user_id, False), ("비밀번호", self.password, True)]
        ):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=6)
            entry = ttk.Entry(body, textvariable=var, width=34, show="•" if hide else "")
            entry.grid(row=row, column=1, padx=(12, 0), pady=6)

        ttk.Label(
            body,
            text="비밀번호는 이 PC의 윈도우 계정에 묶여 암호화 저장됩니다.\n"
            "설정 파일을 다른 PC로 복사해도 열리지 않습니다.",
            foreground="#666",
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        # 설정이 exe 옆이 아니라 사용자 폴더에 저장되므로 찾아갈 길을 만들어준다
        ttk.Button(buttons, text="설정 폴더 열기", command=self._open_folder).pack(side="left")
        ttk.Button(buttons, text="취소", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="저장", command=self._save).pack(side="right", padx=8)

    def _open_folder(self) -> None:
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(APP_DIR)  # noqa: S606 — 사용자가 누른 폴더 열기
        except Exception:
            messagebox.showinfo("설정", f"설정이 저장되는 폴더입니다.\n\n{APP_DIR}", parent=self)

    def _save(self) -> None:
        if not self.user_id.get().strip() or not self.password.get():
            messagebox.showwarning("설정", "아이디와 비밀번호를 모두 입력해주세요.", parent=self)
            return
        config = credentials.load(self.config_path)
        config["mall_url"] = self.mall.get().strip() or credentials.DEFAULT_MALL_URL
        config["login"] = {"id": self.user_id.get().strip(), "password": self.password.get()}
        if not credentials.save(self.config_path, config):
            # 조용히 실패하면 사장님은 '설정하라'는 안내만 무한히 다시 보게 된다
            messagebox.showerror(
                "설정",
                "설정을 저장하지 못했습니다.\n\n"
                "이 PC에서는 비밀번호를 안전하게 보관할 수 없거나,\n"
                "설정 폴더에 쓸 권한이 없습니다.\n\n"
                "담당자에게 알려주세요.",
                parent=self,
            )
            return
        # 계정이 바뀌면 이전 로그인 세션은 버린다
        SESSION_PATH.unlink(missing_ok=True)
        self.destroy()


def _can_write(folder: Path) -> bool:
    """설정을 저장할 수 있는 폴더인지. Program Files 등에 두면 여기서 걸린다."""
    probe = folder / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def selftest() -> int:
    """`WellrootOrder.exe --selftest` — 빌드된 exe가 실제로 동작하는지 확인한다.

    창을 띄우지 않고 브라우저까지 실제로 실행해 본다. onefile 빌드는
    Playwright의 Node 드라이버 경로에서 깨지는 일이 잦아서, 배포 전에 이걸 꼭 돌린다.
    결과는 exe 옆 `selftest.log`에 남긴다(--windowed라 콘솔 출력이 없다).
    """
    import traceback

    import storage

    log_path = SELFTEST_LOG
    lines = [
        f"{APP_NAME} {VERSION} 자가진단",
        f"frozen: {storage.is_frozen()}",
        f"설정 폴더: {APP_DIR}",
        f"  휴대용 모드(exe 옆 저장): {storage.is_portable()}",
        f"  쓰기 가능: {_can_write(APP_DIR)}",
    ]

    try:
        from playwright.sync_api import sync_playwright

        import browser as browser_launcher

        lines.append("playwright 임포트 OK")
        with sync_playwright() as p:
            b, channel = browser_launcher.launch(p, headless=True, slow_mo=0)
            lines.append(f"브라우저 실행 OK — {channel} / {b.version}")
            page = b.new_page()
            page.goto("https://wellrootb2b.com", wait_until="domcontentloaded", timeout=30000)
            lines.append(f"페이지 로드 OK — {page.title()[:60]}")
            b.close()

        import credentials
        from excel_reader import COLUMNS

        token = credentials.encrypt("selftest")
        lines.append(f"비밀번호 암호화 OK — 왕복 일치: {credentials.decrypt(token) == 'selftest'}")
        lines.append(f"엑셀 컬럼 {len(COLUMNS)}개 로드 OK")
        lines.append("결과: 정상")
        code = 0
    except Exception:
        lines.append("결과: 실패")
        lines.append(traceback.format_exc())
        code = 1

    log_path.write_text("\n".join(lines), encoding="utf-8")
    return code


def main() -> int:
    """--windowed exe는 콘솔이 없어 예외가 조용히 사라진다.

    시작하자마자 죽으면 사장님 눈에는 '눌렀는데 아무 일도 없음'으로만 보인다.
    그래서 어떤 실패든 파일로 남기고 창으로 알린다.
    """
    if "--selftest" in sys.argv:
        return selftest()

    try:
        OrderApp().mainloop()
        return 0
    except Exception:
        import traceback

        detail = traceback.format_exc()
        try:
            ERROR_LOG.write_text(detail, encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror(
                APP_NAME,
                "프로그램을 시작하지 못했습니다.\n\n"
                f"{detail.strip().splitlines()[-1]}\n\n"
                f"자세한 내용은 아래 파일을 보내주세요:\n{ERROR_LOG}",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
