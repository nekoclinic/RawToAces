# RawToAces

raw画像や通常画像を、リニアACEScg（16bit TIFF / 32bit float EXR）へ変換するGUIツール。

## セットアップ

```bash
pip install -r requirements.txt
```

## 使い方

```bash
python raw_to_aces_gui.py
```

- 「ファイル追加」で画像を選ぶ（複数選択可）
- 一覧から選択（Ctrl+クリックで複数選択）、「選択を削除」で除去
- 出力形式・圧縮・保存先を設定して「変換開始」

## 出力

- 保存先: 各画像フォルダ内の `converted_aces/`（指定フォルダも可）
- ファイル名: `<元ファイル名>.tif` / `.exr`（同名があれば `-1`, `-2` …）
- 色: ACEScg（AP1、D60）固定

## exeのビルド（Windows）

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean RawToAces.spec
```

出力: `dist/RawToAces.exe`（確認: `dist/RawToAces.exe --selftest`）

## 注意

- リニアACEScgのため、ビューアでは暗く見えます（OCIO対応アプリで確認してください）。
- TIFFをBlenderで読み込む場合は、カラースペースを `Non-Color` または `ACEScg` に変更してください。
