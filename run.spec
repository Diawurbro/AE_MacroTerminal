# PyInstaller spec for Roblox TD Macro
# Build with:  pyinstaller run.spec --noconfirm

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[("config.yaml", ".")],
    hiddenimports=[
        "win32gui", "win32api", "win32con",
        "mss", "mss.windows",
        "cv2", "numpy", "yaml", "requests",
        "pytesseract", "PIL", "sqlite3",
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtCharts",
        "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtSql",
        "tkinter", "matplotlib", "scipy", "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="run",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="run",
)
