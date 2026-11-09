# RawToAces

raw画像を選択して、ACEScg（リニア）へ変換するツール。

- 入力: raw（DNG / CR3 / NEF など LibRaw対応形式）と通常画像（JPEG / PNG / TIFF / BMP / WebP）
  - 通常画像は sRGB としてリニア化し、ACEScg へ変換します
- 出力形式: 16bit TIFF / 32bit float EXR

## セットアップ

```bash
pip install -r requirements.txt
```

## 使い方

ダブルクリック相当（ダイアログで複数選択）:

```bash
python raw_to_aces.py
```

引数で直接指定:

```bash
python raw_to_aces.py IMG_0001.CR3 IMG_0002.CR3
python raw_to_aces.py --format exr photo.jpg
python raw_to_aces.py --format exr IMG_0001.CR3
```

### オプション

| オプション | 既定 | 説明 |
| --- | --- | --- |
| `--format {tif,exr}` | `tif` | 出力形式（TIFF 16bit / EXR 32bit float） |
| `--compress {lzw,deflate,none}` | `lzw` | TIFF圧縮方式（EXRはZIP固定） |
| `--outdir DIR` | - | 出力先を固定（既定は各画像フォルダ内の `convert_aces/`） |
| `--skip-existing` | off | 出力済みファイルをスキップ |
| `--no-gui` | off | ファイル選択ダイアログを開かない |

## 出力

- 保存先: 選択した画像と同じフォルダ内の `convert_aces/`（`--outdir` で変更可）
- ファイル名: `<元ファイル名>.tif` / `<元ファイル名>.exr`
- 色: ACEScg（AP1、D60）固定
- 変換: LibRaw がカメラRGB → XYZ → ACES（D60）へ変換（rawpy の `ColorSpace.ACES`）
- 通常画像: sRGB（8bit / 16bit）として逆ガンマ → リニアsRGB → ACEScg（D60）へ変換
- TIFF: 16bit / 3ch / リニア、Photometric=RGB、0..1にクリップ
- EXR: 32bit float / 3ch / リニア、ZIP圧縮、値はクリップしない
  （AP0→AP1変換で1を超える値や負値はそのまま保持）

## GUI

```bash
python raw_to_aces_gui.py
```

一覧はサムネイルのグリッド表示で、画像の下にファイル名と状態を表示します。
クリックで選択（Ctrl+クリックで複数選択）し、選んだ形式でまとめて変換します。

サムネイルは「埋め込みサムネイル → 縮小現像 → ベイヤー簡易表示」の順で生成するため、
各社raw（Canon / Nikon / Sony / Fuji など LibRaw対応形式）でも表示できます。

## exeのビルド（Windows）

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean RawToAces.spec
```

- 出力: `dist/RawToAces.exe`（1ファイル・コンソールなし）
- 同梱物の確認: `dist/RawToAces.exe --selftest`（rawpy / numpy / opencv / tkinter / EXRコーデックを確認し、問題なければ終了コード0）
- ビルドには `RawToAces.spec` が必要

## 注意

- リニアACEScgのため、そのままビューアで開くと暗く見えるのが正常です。
  表示確認は After Effects / DaVinci Resolve / OCIO 対応アプリなどで行ってください。
- ハイライトは LibRaw のクリップ処理により白レベルで頭打ちになります。
