# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

ROOT_DIR = os.path.abspath(os.path.join(SPECPATH, '..'))

# NVIDIA CUDA packages
nvidia_packages = [
    'nvidia.cublas',
    'nvidia.cuda_nvrtc',
    'nvidia.cuda_runtime',
    'nvidia.cudnn',
    'nvidia.cufft',
    'nvidia.curand',
    'nvidia.nvjitlink',
]

nvidia_binaries = []
nvidia_datas = []
nvidia_hiddenimports = []

for package in nvidia_packages:
    try:
        binaries, datas, hiddenimports = collect_all(package)
        nvidia_binaries.extend(binaries)
        nvidia_datas.extend(datas)
        nvidia_hiddenimports.extend(hiddenimports)
    except Exception:
        pass

a = Analysis(
    [os.path.join(ROOT_DIR, 'main.py')],
    pathex=[ROOT_DIR],
    binaries=nvidia_binaries,
    datas=[
        (os.path.join(ROOT_DIR, 'assets'), 'assets'),
        (os.path.join(ROOT_DIR, 'src'), 'src'),
    ] + nvidia_datas,
    hiddenimports=[
        'onnxruntime',
        'onnxruntime.capi',
        'onnxruntime.capi.onnxruntime_pybind11_state',
        'PySide6.QtSvg',
    ] + nvidia_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Only remove unused Qt components
forbidden_keywords = [
    'libQt6OpenGL',
    'libQt6Pdf',
    'libQt6Qml',
    'libQt6Quick',
    'libQt6VirtualKeyboard',
    'translations',
]

filtered_binaries = []
for b in a.binaries:
    dest_path = b[0].lower()
    if not any(kw.lower() in dest_path for kw in forbidden_keywords):
        filtered_binaries.append(b)
a.binaries = filtered_binaries

filtered_datas = []
for d in a.datas:
    dest_path = d[0].lower()
    if not any(kw.lower() in dest_path for kw in forbidden_keywords):
        filtered_datas.append(d)
a.datas = filtered_datas

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MangaCleaner_GPU',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT_DIR, 'assets', 'icon.ico')],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MangaCleaner_GPU',
)
