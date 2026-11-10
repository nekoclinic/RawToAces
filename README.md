# RawToAces

raw画像を選択して、ACEScg（リニア）へ変換するGUIツール。

- 入力: raw（DNG / CR3 / NEF など LibRaw対応形式）と通常画像（JPEG / PNG / TIFF / BMP / WebP）
  - 通常画像は sRGB としてリニア化し、ACEScg へ変換します（16bit TIFF も sRGB 前提）
  - EXRなどのfloat画像は入力に未対応です
- 出力形式: 16bit TIFF / 32bit float EXR

## セットアップ

```bash
pip install -r requirements.txt
```

EXRの色域情報（ACEScg）付与に OpenEXR を使用します。

## 使い方

```bash
python raw_to_aces_gui.py
```

1. 「ファイル追加」で変換する画像を選ぶ（複数選択可）
2. 一覧はサムネイルのグリッド表示。クリックで選択（Ctrl+クリックで複数選択）、「選択を削除」で取り除く
3. 設定で出力形式・圧縮・保存先を選ぶ
4. 「変換開始」でまとめて変換

サムネイルは「埋め込みサムネイル → 縮小現像 → ベイヤー簡易表示」の順で生成するため、
各社raw（Canon / Nikon / Sony / Fuji など LibRaw対応形式）でも表示できます。

### 設定

| 項目 | 内容 |
| --- | --- |
| 出力形式 | `OpenEXR (32bit float)`（既定） / `TIFF (16bit)` |
| EXR圧縮 | ZIP（既定・可逆） / PXR24（軽量） / DWAA（最小・非可逆） |
| TIFF圧縮 | LZW / Deflate / 圧縮なし |
| 保存先 | 各画像のフォルダ内の `convert_aces/`、または指定フォルダ |
| 出力済みファイルはスキップ | 同名ファイルがある場合にスキップ（オフなら連番で保存。同じ実行内で作成した出力もスキップ対象） |

## 出力

- 保存先: 各画像と同じフォルダ内の `convert_aces/`（指定フォルダにも変更可）
- ファイル名: `<元ファイル名>.tif` / `<元ファイル名>.exr`
  （同名ファイルがある場合は `-1`, `-2` … を付与）
- 色: ACEScg（AP1、D60）固定
- 変換: LibRaw がカメラRGB → XYZ → ACES（D60）へ変換（rawpy の `ColorSpace.ACES`）
- 通常画像: sRGB（8bit / 16bit）として逆ガンマ → リニアsRGB → ACEScg（D60）へ変換
- TIFF: 16bit / 3ch / リニア、Photometric=RGB、0..1にクリップ
- EXR: 32bit float / 3ch / リニア、値はクリップしない
  （AP0→AP1変換で1を超える値や負値はそのまま保持）
  ACEScg（AP1）の chromaticities を埋め込むため、ACES OCIO設定のBlender等では
  ACEScgとして読み込まれます
  - 圧縮は既定の **ZIP**（完全可逆）
  - **PXR24** は16bit入力に対して十分な精度（誤差約1/65535）で、ZIPの約6割のサイズ
  - **DWAA** はさらに小さい（実測で約1/3以下）が非可逆

## Blenderで読み込む

- **EXR（推奨）**: そのまま読み込めます。既定のBlender設定ではカラースペースが
  `Linear Rec.709` になるため、ACESで運用する場合は ACES OCIO 設定を入れて
  `ACEScg` を選んでください。
- **TIFF**: 16bitリニアのため、Blenderの既定（sRGBとして解釈）では暗く見えます。
  画像のカラースペースを `Non-Color` または `ACEScg` に変更してください。

## exeのビルド（Windows）

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean RawToAces.spec
```

- 出力: `dist/RawToAces.exe`（1ファイル・コンソールなし）
- 同梱物の確認: `dist/RawToAces.exe --selftest`（rawpy / numpy / opencv / tkinter / EXRコーデックを確認し、問題なければ終了コード0）
- ビルドには `RawToAces.spec` と `icon.ico` が必要

## 注意

- リニアACEScgのため、そのままビューアで開くと暗く見えるのが正常です。
  表示確認は After Effects / DaVinci Resolve / OCIO 対応アプリなどで行ってください。
- ハイライトは LibRaw のクリップ処理により白レベルで頭打ちになります。
- 大きな画像（40MP超など）では変換時に数百MB〜1GB程度のメモリを使います。
  メモリ不足になる場合は TIFF（16bit）出力にすると負荷を抑えられます。
