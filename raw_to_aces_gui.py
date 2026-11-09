#!/usr/bin/env python3
# raw画像をACEScgへ変換するGUIツール
#
# 使い方:
#   python raw_to_aces_gui.py
#
# 「ファイル追加」で画像を選び、「変換開始」でリニアACEScgへ変換する
# 出力形式は16bit TIFF / 32bit float EXRから選べる
# 保存先は既定で各画像フォルダ内の convert_aces/、設定で固定フォルダも選べる

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from raw_to_aces import FORMAT_LABELS, OUTPUT_DIR_NAME, RAW_EXTENSIONS, convert_file, describe

# 選択肢（キー, 表示名）
FORMAT_OPTIONS = (("tif", FORMAT_LABELS["tif"]), ("exr", FORMAT_LABELS["exr"]))
WB_OPTIONS = (("camera", "撮影時 (camera)"), ("auto", "自動 (auto)"), ("none", "なし (none)"))
COMPRESSION_OPTIONS = (("lzw", "LZW"), ("deflate", "Deflate"), ("none", "圧縮なし"))

# ファイル選択ダイアログ用のパターン
RAW_PATTERN = " ".join(f"*{ext}" for ext in RAW_EXTENSIONS)


def enable_dpi_awareness() -> None:
    # Windowsの高DPI環境で文字がぼやけないようにする
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.files: list[Path] = []
        self.queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self.reserved: set[Path] = set()
        self.last_out_dir: Path | None = None

        # 表示名 -> キー の対応表（スレッドからtk変数を読まないよう開始時に確定させる）
        self.format_map = {label: key for key, label in FORMAT_OPTIONS}
        self.wb_map = {label: key for key, label in WB_OPTIONS}
        self.comp_map = {label: key for key, label in COMPRESSION_OPTIONS}

        root.title("raw → ACEScg 変換 (16bit TIFF / 32bit EXR)")
        root.minsize(860, 660)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=3)
        main.rowconfigure(4, weight=2)

        self._build_toolbar(main)
        self._build_file_list(main)
        self._build_settings(main)
        self._build_progress(main)
        self._build_log(main)
        self._build_actions(main)

        self._sync_outmode()
        self.root.after(80, self._poll)

    # ---- 画面の組み立て ----

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.add_file_btn = ttk.Button(bar, text="ファイル追加", command=self.add_files)
        self.add_file_btn.pack(side="left")
        self.add_folder_btn = ttk.Button(bar, text="フォルダ追加", command=self.add_folder)
        self.add_folder_btn.pack(side="left", padx=(6, 0))
        self.remove_btn = ttk.Button(bar, text="選択を削除", command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=(6, 0))
        self.clear_btn = ttk.Button(bar, text="すべてクリア", command=self.clear_all)
        self.clear_btn.pack(side="left", padx=(6, 0))
        self.count_label = ttk.Label(bar, text="0件")
        self.count_label.pack(side="right")

    def _build_file_list(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            frame,
            columns=("file", "folder", "status"),
            show="headings",
            height=10,
            selectmode="extended",
        )
        self.tree.heading("file", text="ファイル")
        self.tree.heading("folder", text="フォルダ")
        self.tree.heading("status", text="状態")
        self.tree.column("file", width=280, stretch=True, anchor="w")
        self.tree.column("folder", width=420, stretch=True, anchor="w")
        self.tree.column("status", width=90, stretch=False, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def _build_settings(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="設定", padding=8)
        box.grid(row=2, column=0, sticky="ew", pady=6)
        box.columnconfigure(3, weight=1)

        ttk.Label(box, text="出力形式").grid(row=0, column=0, sticky="w")
        self.format_var = tk.StringVar(value=FORMAT_OPTIONS[0][1])
        self.format_combo = ttk.Combobox(
            box, textvariable=self.format_var, state="readonly", width=18,
            values=[label for _, label in FORMAT_OPTIONS],
        )
        self.format_combo.grid(row=0, column=1, sticky="w", padx=(6, 18))
        self.format_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_format())

        ttk.Label(box, text="ホワイトバランス").grid(row=0, column=2, sticky="w")
        self.wb_var = tk.StringVar(value=WB_OPTIONS[0][1])
        self.wb_combo = ttk.Combobox(
            box, textvariable=self.wb_var, state="readonly", width=18,
            values=[label for _, label in WB_OPTIONS],
        )
        self.wb_combo.grid(row=0, column=3, sticky="w", padx=(6, 18))

        ttk.Label(box, text="TIFF圧縮").grid(row=0, column=4, sticky="w")
        self.comp_var = tk.StringVar(value=COMPRESSION_OPTIONS[0][1])
        self.comp_combo = ttk.Combobox(
            box, textvariable=self.comp_var, state="readonly", width=12,
            values=[label for _, label in COMPRESSION_OPTIONS],
        )
        self.comp_combo.grid(row=0, column=5, sticky="w", padx=(6, 0))

        # 保存先の選択
        self.outmode_var = tk.StringVar(value="same")
        self.same_radio = ttk.Radiobutton(
            box,
            text=f"各画像のフォルダの {OUTPUT_DIR_NAME}/",
            variable=self.outmode_var,
            value="same",
            command=self._sync_outmode,
        )
        self.same_radio.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.custom_radio = ttk.Radiobutton(
            box,
            text="指定フォルダ:",
            variable=self.outmode_var,
            value="custom",
            command=self._sync_outmode,
        )
        self.custom_radio.grid(row=1, column=2, sticky="w", pady=(10, 0))

        self.outdir_var = tk.StringVar()
        self.outdir_entry = ttk.Entry(box, textvariable=self.outdir_var, width=40)
        self.outdir_entry.grid(row=1, column=3, columnspan=2, sticky="ew", pady=(10, 0))

        self.browse_btn = ttk.Button(box, text="参照...", command=self.browse_outdir)
        self.browse_btn.grid(row=1, column=5, sticky="w", padx=(6, 0), pady=(10, 0))

        self.skip_var = tk.BooleanVar(value=False)
        self.skip_check = ttk.Checkbutton(
            box, text="出力済みファイルはスキップ", variable=self.skip_var,
        )
        self.skip_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Label(
            box, text="EXR: 32bit float / ZIP圧縮・値はクリップなし",
            foreground="gray",
        ).grid(row=2, column=3, columnspan=3, sticky="w", pady=(10, 0))

    def _build_progress(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew")
        self.status_label = ttk.Label(frame, text="ファイルを追加してください")
        self.status_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _build_log(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="ログ", padding=4)
        frame.grid(row=4, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log = tk.Text(frame, height=7, wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _build_actions(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=5, column=0, sticky="ew", pady=(8, 0))

        self.start_btn = ttk.Button(bar, text="変換開始", command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bar, text="中止", command=self.request_cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(6, 0))
        self.open_btn = ttk.Button(
            bar, text="出力フォルダを開く", command=self.open_outdir, state="disabled",
        )
        self.open_btn.pack(side="right")

    # ---- ファイルの追加・削除 ----

    def add_files(self) -> None:
        picked = filedialog.askopenfilenames(
            parent=self.root,
            title="raw画像を選択（複数選択可）",
            filetypes=[("raw画像", RAW_PATTERN), ("すべてのファイル", "*.*")],
        )
        self._add_paths([Path(p) for p in picked])

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self.root, title="フォルダを選択")
        if not folder:
            return
        found = sorted(
            p for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS
        )
        if not found:
            messagebox.showinfo("フォルダ追加", "raw画像が見つかりませんでした", parent=self.root)
            return
        self._add_paths(found)

    def _add_paths(self, paths: list[Path]) -> None:
        seen = {p.resolve() for p in self.files}
        added = 0
        for path in paths:
            if not path.is_file():
                continue
            key = path.resolve()
            if key in seen:
                continue
            seen.add(key)
            self.files.append(path)

            # ツリーの行IDにはパス文字列を使う
            self.tree.insert(
                "", "end", iid=str(path),
                values=(path.name, str(path.parent), "待機"),
            )
            added += 1

        self._update_count()
        if added:
            self._log(f"{added}件を追加しました")

    def remove_selected(self) -> None:
        if self.running:
            return
        for iid in self.tree.selection():
            self.tree.delete(iid)
            path = Path(iid)
            if path in self.files:
                self.files.remove(path)
            self.reserved.discard(path)
        self._update_count()

    def clear_all(self) -> None:
        if self.running:
            return
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self.reserved.clear()
        self.last_out_dir = None
        self.open_btn.configure(state="disabled")
        self.progress.configure(value=0)
        self.status_label.configure(text="ファイルを追加してください")
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.configure(text=f"{len(self.files)}件")

    # ---- 設定 ----

    def _sync_outmode(self) -> None:
        custom = self.outmode_var.get() == "custom"
        state = "normal" if custom else "disabled"
        self.outdir_entry.configure(state=state)
        self.browse_btn.configure(state=state)

    def _sync_format(self) -> None:
        # 圧縮設定はTIFFのときだけ有効にする
        enabled = self.format_var.get() == FORMAT_OPTIONS[0][1] and not self.running
        self.comp_combo.configure(state="readonly" if enabled else "disabled")

    def browse_outdir(self) -> None:
        folder = filedialog.askdirectory(parent=self.root, title="出力フォルダを選択")
        if folder:
            self.outdir_var.set(folder)

    # ---- 変換の開始と実行 ----

    def start(self) -> None:
        if self.running:
            return
        if not self.files:
            messagebox.showwarning("変換", "変換する画像を追加してください", parent=self.root)
            return

        # 出力先を決める（固定フォルダ指定なら作成を試す）
        out_dir_fixed: Path | None = None
        if self.outmode_var.get() == "custom":
            text = self.outdir_var.get().strip()
            if not text:
                messagebox.showwarning("変換", "出力フォルダを指定してください", parent=self.root)
                return
            out_dir_fixed = Path(text)
            try:
                out_dir_fixed.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror(
                    "変換", f"出力フォルダを作成できません:\n{exc}", parent=self.root,
                )
                return

        # スレッドに渡す設定値をここで確定させる
        fmt = self.format_map[self.format_var.get()]
        wb = self.wb_map[self.wb_var.get()]
        compress = self.comp_map[self.comp_var.get()]
        skip_existing = self.skip_var.get()

        self.running = True
        self.cancel_event.clear()
        self.reserved = set()
        self.last_out_dir = None
        self._set_running(True)
        self.progress.configure(maximum=len(self.files), value=0)
        self.status_label.configure(text="変換中...")
        self._log(
            f"変換を開始しました（{len(self.files)}件 / "
            f"ACEScg {FORMAT_LABELS[fmt]}）"
        )

        worker = threading.Thread(
            target=self._worker,
            args=(list(self.files), out_dir_fixed, fmt, wb, compress, skip_existing),
            daemon=True,
        )
        worker.start()

    def _worker(
        self,
        files: list[Path],
        out_dir_fixed: Path | None,
        fmt: str,
        wb: str,
        compress: str,
        skip_existing: bool,
    ) -> None:
        done = skipped = failed = 0

        for n, path in enumerate(files, 1):
            if self.cancel_event.is_set():
                self.queue.put(("log", "中止しました"))
                break

            self.queue.put(("status", str(path), "変換中"))
            out_dir = out_dir_fixed if out_dir_fixed else path.parent / OUTPUT_DIR_NAME

            try:
                out_path = convert_file(
                    path,
                    fmt=fmt,
                    wb=wb,
                    compress=compress,
                    out_dir=out_dir,
                    skip_existing=skip_existing,
                    reserved=self.reserved,
                )
                done += 1
                self.queue.put(("status", str(path), "完了"))
                self.queue.put(("log", f"完了: {out_path}"))
                self.queue.put(("outdir", str(out_dir)))
            except FileExistsError:
                skipped += 1
                self.queue.put(("status", str(path), "スキップ"))
                self.queue.put(("log", f"スキップ（出力済み）: {path.name}"))
            except Exception as exc:
                failed += 1
                self.queue.put(("status", str(path), "エラー"))
                self.queue.put(("log", f"エラー: {path.name}: {describe(exc)}"))

            self.queue.put(("progress", n))

        self.queue.put(("done", {"done": done, "skipped": skipped, "failed": failed}))

    def _poll(self) -> None:
        # ワーカースレッドからのメッセージをGUI側で処理する
        while True:
            try:
                message = self.queue.get_nowait()
            except queue.Empty:
                break

            kind = message[0]
            if kind == "status":
                self._set_status(Path(message[1]), message[2])
            elif kind == "log":
                self._log(message[1])
            elif kind == "progress":
                self.progress.configure(value=message[1])
            elif kind == "outdir":
                self.last_out_dir = Path(message[1])
                self.open_btn.configure(state="normal")
            elif kind == "done":
                self._finish(message[1])

        self.root.after(80, self._poll)

    def _finish(self, counts: dict[str, int]) -> None:
        self.running = False
        self._set_running(False)
        summary = (
            f"完了: {counts['done']}件 / "
            f"スキップ: {counts['skipped']}件 / "
            f"失敗: {counts['failed']}件"
        )
        self.status_label.configure(text=summary)
        self._log(summary)

        if counts["done"]:
            self.open_btn.configure(state="normal")

        if counts["failed"]:
            messagebox.showwarning(
                "ACES変換", summary + "\n\n詳細はログを確認してください。", parent=self.root,
            )
        else:
            messagebox.showinfo("ACES変換", summary, parent=self.root)

    def request_cancel(self) -> None:
        if not self.running:
            return
        self.cancel_event.set()
        self._log("中止を受け付けました（現在のファイルの完了後に停止します）")
        self.cancel_btn.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        combo_state = "disabled" if running else "readonly"

        for button in (self.add_file_btn, self.add_folder_btn, self.remove_btn, self.clear_btn):
            button.configure(state=state)
        self.start_btn.configure(state=state)
        self.cancel_btn.configure(state="normal" if running else "disabled")
        self.skip_check.configure(state=state)
        for combo in (self.format_combo, self.wb_combo):
            combo.configure(state=combo_state)
        self.same_radio.configure(state=state)
        self.custom_radio.configure(state=state)

        if running:
            self.outdir_entry.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
        else:
            self._sync_outmode()
        self._sync_format()

    # ---- 表示の更新 ----

    def _set_status(self, path: Path, text: str) -> None:
        iid = str(path)
        if self.tree.exists(iid):
            self.tree.set(iid, "status", text)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def open_outdir(self) -> None:
        folder = self.last_out_dir
        if folder is None or not folder.is_dir():
            messagebox.showinfo("出力フォルダ", "出力フォルダがまだありません", parent=self.root)
            return
        try:
            os.startfile(str(folder))
        except AttributeError:
            # Windows以外
            subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("出力フォルダ", str(exc), parent=self.root)


def main() -> int:
    # ビルド確認用: 依存モジュールが同梱されているかを確かめて終了する
    if "--selftest" in sys.argv:
        import tempfile

        import cv2  # noqa: F401
        import numpy as np
        import rawpy  # noqa: F401
        from raw_to_aces import write_exr32

        # tkinter（Tcl/Tk）が同梱されているかも確認する
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()

        # EXRコーデック（32bit float）が動くか書き出し→読み込みで確認する
        with tempfile.TemporaryDirectory() as tmp:
            exr = Path(tmp) / "probe.exr"
            write_exr32(np.zeros((2, 2, 3), np.float32), exr)
            data = cv2.imread(str(exr), cv2.IMREAD_UNCHANGED)
            if data is None or data.dtype != np.float32:
                return 3
        return 0

    enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
