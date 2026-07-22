"""NURC自動生成ツール GUI(tkinter)。

マネージャーがPython無しで使えるよう、単一の.exeに固めることを想定した画面。
大会URLと(任意で)対象日を入力して「NURC生成」を押すと、結果報告文を生成し
テキスト欄に表示する。「全文コピー」でクリップボードへ、「保存」でtxt出力。

依存は標準ライブラリのみ(tkinter)。生成ロジックは nurc_gen.pipeline を利用。
ネットワーク取得中もUIが固まらないよう別スレッドで実行する。
"""

from __future__ import annotations

import queue
import threading
from datetime import date, datetime
from pathlib import Path
from tkinter import (BOTH, END, DISABLED, NORMAL, StringVar, Tk, WORD,
                     filedialog, messagebox, ttk)
from tkinter.scrolledtext import ScrolledText

from nurc_gen.pipeline import generate_nurc
from nurc_gen.resources import external_config_path

_SAMPLE_URLS = (
    "https://karal.jp/news_flash/result.htm",
    "https://www.jara.or.jp/race/2025/2025intercollege.html",
)


class NurcApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title("NURC生成ツール")
        root.geometry("760x620")
        root.minsize(640, 520)

        self._result_queue: "queue.Queue" = queue.Queue()
        self._build_widgets()

    # ---------------- 画面構築 ----------------
    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=BOTH, expand=True)

        ttk.Label(frm, text="大会結果ページのURL").grid(row=0, column=0, sticky="w", **pad)
        self.url_var = StringVar()
        url_entry = ttk.Entry(frm, textvariable=self.url_var)
        url_entry.grid(row=1, column=0, columnspan=3, sticky="we", **pad)
        url_entry.focus()

        ttk.Label(frm, text="対象日 (YYYY-MM-DD / 空欄=最新日を自動)").grid(
            row=2, column=0, sticky="w", **pad)
        self.date_var = StringVar()
        ttk.Entry(frm, textvariable=self.date_var, width=18).grid(
            row=3, column=0, sticky="w", **pad)

        self.run_btn = ttk.Button(frm, text="NURC生成", command=self._on_generate)
        self.run_btn.grid(row=3, column=1, sticky="w", **pad)

        self.status_var = StringVar(value="URLを入力して「NURC生成」を押してください。")
        ttk.Label(frm, textvariable=self.status_var, foreground="#555").grid(
            row=4, column=0, columnspan=3, sticky="w", **pad)

        self.output = ScrolledText(frm, wrap=WORD, font=("Meiryo", 10), height=22)
        self.output.grid(row=5, column=0, columnspan=3, sticky="nsew", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=3, sticky="we", **pad)
        self.copy_btn = ttk.Button(btns, text="全文コピー", command=self._on_copy,
                                   state=DISABLED)
        self.copy_btn.pack(side="left", padx=4)
        self.save_btn = ttk.Button(btns, text="テキスト保存", command=self._on_save,
                                   state=DISABLED)
        self.save_btn.pack(side="left", padx=4)
        ttk.Label(btns, text=f"設定ファイル: {external_config_path()}",
                  foreground="#888").pack(side="right", padx=4)

        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(5, weight=1)

    # ---------------- 生成処理 ----------------
    def _parse_date(self) -> date | None:
        s = self.date_var.get().strip()
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("対象日は YYYY-MM-DD 形式で入力してください（例 2026-07-04）。")

    def _on_generate(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("入力エラー", "大会結果ページのURLを入力してください。")
            return
        try:
            target = self._parse_date()
        except ValueError as exc:
            messagebox.showwarning("入力エラー", str(exc))
            return

        self.run_btn.config(state=DISABLED)
        self.copy_btn.config(state=DISABLED)
        self.save_btn.config(state=DISABLED)
        self.status_var.set("解析中… ページを取得しています（数十秒かかることがあります）")
        self._set_output("")

        threading.Thread(target=self._worker, args=(url, target), daemon=True).start()
        self.root.after(120, self._poll_result)

    def _worker(self, url: str, target: date | None) -> None:
        try:
            result = generate_nurc(url, target)
            self._result_queue.put(("ok", result))
        except Exception as exc:  # noqa: BLE001 - UIへ通知
            self._result_queue.put(("error", exc))

    def _poll_result(self) -> None:
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.root.after(120, self._poll_result)
            return

        self.run_btn.config(state=NORMAL)
        if kind == "error":
            self.status_var.set("生成に失敗しました。")
            messagebox.showerror("エラー", str(payload))
            return

        result = payload
        self._set_output(result.text)
        site_ja = "関西選手権" if result.site == "karal" else "インカレ"
        day = result.resolved_target
        day_str = f"{day:%Y-%m-%d}" if day else "（日付不明）"
        auto = "" if result.target_specified else "（自動判定）"

        if result.total_races == 0:
            self.status_var.set(
                f"{site_ja}として認識しましたが、レースを1件も取得できませんでした。"
                "大会の「結果一覧（トップ）ページ」のURLかご確認ください。"
            )
        elif result.nagoya_races == 0:
            self.status_var.set(
                f"{site_ja}として解析: 全{result.total_races}レース中、"
                "名古屋大学の出場が見つかりませんでした。URLをご確認ください。"
            )
        elif result.day_result_races == 0:
            # 大会には名大が出ているが、選んだ対象日には結果が無い
            self.status_var.set(
                f"{site_ja}: 対象日 {day_str}{auto} に名古屋大学の結果がありません。"
                f"（大会全体では{result.nagoya_races}件出場）対象日をご確認ください。"
            )
            self.copy_btn.config(state=NORMAL)
            self.save_btn.config(state=NORMAL)
        else:
            self.status_var.set(
                f"{site_ja} 対象日 {day_str}{auto}: 名古屋大学の結果"
                f"{result.day_result_races}件を本文に反映しました。"
            )
            self.copy_btn.config(state=NORMAL)
            self.save_btn.config(state=NORMAL)

    # ---------------- 出力操作 ----------------
    def _set_output(self, text: str) -> None:
        self.output.config(state=NORMAL)
        self.output.delete("1.0", END)
        self.output.insert(END, text)

    def _current_text(self) -> str:
        return self.output.get("1.0", END).rstrip("\n")

    def _on_copy(self) -> None:
        text = self._current_text()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("全文をクリップボードにコピーしました。メールに貼り付けてください。")

    def _on_save(self) -> None:
        text = self._current_text()
        if not text:
            return
        default = f"NURC_{date.today():%Y%m%d}.txt"
        path = filedialog.asksaveasfilename(
            title="NURCを保存", defaultextension=".txt",
            initialfile=default, filetypes=[("テキスト", "*.txt"), ("すべて", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(text, encoding="utf-8")
        self.status_var.set(f"保存しました: {path}")


def main() -> None:
    root = Tk()
    NurcApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
