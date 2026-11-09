#!/usr/bin/env python3
# raw画像をACEScgへ変換するCLIツール
#
# 使い方:
#   python raw_to_aces.py                # ファイル選択ダイアログを開く（複数選択可）
#   python raw_to_aces.py a.CR3 b.NEF    # 引数で指定
#   python raw_to_aces.py --format exr *.dng
#
# 出力:
#   各画像と同じフォルダ内の convert_aces/ に <元ファイル名>.tif / .exr として保存する
#   色はリニアACEScg（AP1）固定
#   tif = 16bit / exr = 32bit float

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import rawpy

# pythonw等でstdoutが無い場合もあるのでNoneは無視する
for _stream in (sys.stdout, sys.stderr):
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# OpenCVのEXRコーデックは既定で無効なので、読み込む前に有効化する
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

try:
    import cv2
except ImportError:
    cv2 = None

# 対応するrawの拡張子（ファイル選択ダイアログのフィルタにも使用）
RAW_EXTENSIONS = (
    ".3fr", ".ari", ".arw", ".bay", ".cr2", ".cr3", ".crw", ".dcr", ".dng",
    ".erf", ".fff", ".iiq", ".k25", ".kdc", ".mef", ".mos", ".mrw", ".nef",
    ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2", ".rwl", ".srw", ".x3f",
)

# 出力フォルダ名（画像と同じフォルダ内に作成する）
OUTPUT_DIR_NAME = "convert_aces"

# 出力形式の表示名と拡張子
FORMAT_LABELS = {
    "tif": "TIFF (16bit)",
    "exr": "OpenEXR (32bit float)",
}
FORMAT_EXTENSIONS = {"tif": ".tif", "exr": ".exr"}

# ACES2065-1 (AP0) -> ACEScg (AP1) の変換行列
AP0_TO_AP1 = np.array([
    [1.4514393161, -0.2365107469, -0.2149285693],
    [-0.0765537734, 1.1762296998, -0.0996759264],
    [0.0083161484, -0.0060324498, 0.9977163014],
], dtype=np.float32)

# OpenCVのTIFF圧縮指定値
COMPRESSION = {"lzw": 5, "deflate": 8, "none": 1}


def decode_to_acescg(path: Path, wb: str) -> np.ndarray:
    # rawpy(LibRaw)で現像し、カメラRGB -> XYZ -> ACES(AP0) のリニア16bitを得る
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(
            output_color=rawpy.ColorSpace.ACES,
            gamma=(1, 1),          # リニア（ガンマなし）
            output_bps=16,
            no_auto_bright=True,   # 自動明るさ補正はかけない
            use_camera_wb=(wb == "camera"),
            use_auto_wb=(wb == "auto"),
        )

    # 0..1のリニア値に正規化
    arr = rgb.astype(np.float32) / 65535.0

    # ACES2065-1 (AP0) -> ACEScg (AP1)
    return arr @ AP0_TO_AP1.T


def write_tiff16(rgb: np.ndarray, path: Path, compression: str) -> None:
    # 16bit RGB TIFFとして保存する（0..1にクリップ）
    if cv2 is None:
        raise RuntimeError("OpenCV (opencv-python) が必要です: pip install opencv-python")
    arr = np.rint(np.clip(rgb, 0.0, 1.0) * 65535.0).astype(np.uint16)
    params = [cv2.IMWRITE_TIFF_COMPRESSION, COMPRESSION[compression]]
    # OpenCVはBGR順として扱うため、書き込み時にチャンネルを反転する
    out = np.ascontiguousarray(arr[:, :, ::-1])
    if not cv2.imwrite(str(path), out, params):
        raise RuntimeError(f"TIFFの書き込みに失敗しました: {path}")


def write_exr32(rgb: np.ndarray, path: Path) -> None:
    # 32bit float RGB EXRとして保存する（ZIP圧縮、値はクリップしない）
    if cv2 is None:
        raise RuntimeError("OpenCV (opencv-python) が必要です: pip install opencv-python")
    params = [
        cv2.IMWRITE_EXR_TYPE, cv2.IMWRITE_EXR_TYPE_FLOAT,
        cv2.IMWRITE_EXR_COMPRESSION, cv2.IMWRITE_EXR_COMPRESSION_ZIP,
    ]
    out = np.ascontiguousarray(rgb[:, :, ::-1], dtype=np.float32)
    if not cv2.imwrite(str(path), out, params):
        raise RuntimeError(f"EXRの書き込みに失敗しました: {path}")


def describe(exc: Exception) -> str:
    # rawpyはエラーをbytesで返すことがあるので読みやすい文字列にする
    arg = exc.args[0] if exc.args else exc
    if isinstance(arg, bytes):
        return arg.decode("utf-8", "replace")
    return str(arg)


def convert_file(
    path: Path,
    fmt: str = "tif",
    wb: str = "camera",
    compress: str = "lzw",
    out_dir: Path | None = None,
    skip_existing: bool = False,
    reserved: set[Path] | None = None,
) -> Path:
    # 1ファイルを変換して出力パスを返す
    # skip_existing=Trueで出力済みならFileExistsErrorを送出する
    path = Path(path)
    out_dir = Path(out_dir) if out_dir is not None else path.parent / OUTPUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = FORMAT_EXTENSIONS[fmt]
    out_path = out_dir / f"{path.stem}{ext}"
    if out_path.exists() and skip_existing:
        raise FileExistsError(out_path)

    # 同じ実行内で同名になった場合は連番を付ける
    i = 1
    while reserved is not None and out_path in reserved:
        out_path = out_dir / f"{path.stem}_{i}{ext}"
        i += 1

    rgb = decode_to_acescg(path, wb)
    if fmt == "exr":
        write_exr32(rgb, out_path)
    else:
        write_tiff16(rgb, out_path, compress)

    if reserved is not None:
        reserved.add(out_path)
    return out_path


def pick_files() -> list[Path]:
    # ファイル選択ダイアログ（複数選択可）
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    patterns = " ".join(f"*{ext}" for ext in RAW_EXTENSIONS)
    picked = filedialog.askopenfilenames(
        title="ACESに変換するraw画像を選択（複数選択可）",
        filetypes=[("raw画像", patterns), ("すべてのファイル", "*.*")],
    )
    root.destroy()
    return [Path(p) for p in picked]


def notify(title: str, message: str) -> None:
    # GUI実行時に結果を知らせる（コンソールが無い環境向け）
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message)
        root.destroy()
    except Exception:
        print(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="raw画像をリニアACEScgへ変換し、同じフォルダの "
                    f"{OUTPUT_DIR_NAME}/ に 16bit TIFF / 32bit EXR として保存します。",
    )
    parser.add_argument("files", nargs="*", type=Path, help="raw画像（省略時はダイアログで選択）")
    parser.add_argument("--format", choices=sorted(FORMAT_LABELS), default="tif",
                        help="出力形式 (既定: tif = 16bit TIFF)")
    parser.add_argument("--wb", choices=["camera", "auto", "none"], default="camera",
                        help="ホワイトバランス (既定: camera = 撮影時設定)")
    parser.add_argument("--compress", choices=sorted(COMPRESSION), default="lzw",
                        help="TIFF圧縮 (既定: lzw)")
    parser.add_argument("--outdir", type=Path, default=None,
                        help=f"出力先を固定する (既定: 各画像フォルダの {OUTPUT_DIR_NAME}/)")
    parser.add_argument("--no-gui", action="store_true", help="ファイル選択ダイアログを開かない")
    parser.add_argument("--skip-existing", action="store_true", help="出力済みファイルをスキップする")
    args = parser.parse_args(argv)

    files = list(args.files)
    gui = not files and not args.no_gui

    # ファイル指定が無ければダイアログで選択
    if not files:
        if not gui:
            parser.error("ファイルが指定されていません")
        try:
            files = pick_files()
        except Exception as exc:
            print(f"ファイル選択ダイアログを開けませんでした: {describe(exc)}")
            print("パスを引数で指定してください: python raw_to_aces.py image.CR3")
            return 1
        if not files:
            print("ファイルが選択されなかったため終了します。")
            return 1

    print(f"出力: {FORMAT_LABELS[args.format]} / リニア ACEScg (AP1)")

    reserved: set[Path] = set()
    done, skipped, failed = [], [], []

    for n, path in enumerate(files, 1):
        print(f"[{n}/{len(files)}] {path.name}")

        if not path.is_file():
            print("  エラー: ファイルが見つかりません")
            failed.append((path, OSError(f"ファイルが見つかりません: {path}")))
            continue

        try:
            t0 = time.perf_counter()
            out_path = convert_file(
                path,
                fmt=args.format,
                wb=args.wb,
                compress=args.compress,
                out_dir=args.outdir,
                skip_existing=args.skip_existing,
                reserved=reserved,
            )
            print(f"  変換完了: {out_path}  ({time.perf_counter() - t0:.1f}秒)")
            done.append(out_path)
        except FileExistsError:
            print("  スキップ（出力済み）")
            skipped.append(path)
        except Exception as exc:
            print(f"  エラー: {describe(exc)}")
            failed.append((path, exc))

    print(f"\n完了: {len(done)}件 / スキップ: {len(skipped)}件 / 失敗: {len(failed)}件")
    for path, exc in failed:
        print(f"  失敗: {path.name} - {describe(exc)}")

    if gui:
        lines = [f"変換: {len(done)}件", f"スキップ: {len(skipped)}件", f"失敗: {len(failed)}件"]
        if failed:
            lines.append("")
            lines += [f"{p.name}: {describe(e)}" for p, e in failed[:10]]
        notify("ACES変換", "\n".join(lines))

    return 0 if done or skipped else 1


if __name__ == "__main__":
    sys.exit(main())
