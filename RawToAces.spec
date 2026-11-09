# -*- mode: python ; coding: utf-8 -*-
import os
import struct

from PyInstaller.utils.hooks import collect_all


def _blank_icon(path):
    # アイコンなし（透明な1x1 ICO）をビルド時に生成する
    size = 16
    xor = bytes(size * size * 4)
    mask = b"\xff" * (((size + 31) // 32) * 4 * size)
    bmp = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0,
    )
    image = bmp + xor + mask
    entry = struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(image), 22)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, 1) + entry + image)
    return path


icon_path = _blank_icon(os.path.join(SPECPATH, ".blank_icon.ico"))

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('rawpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['raw_to_aces_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RawToAces',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

# ビルド後に一時アイコンファイルを削除する
if os.path.exists(icon_path):
    os.remove(icon_path)
