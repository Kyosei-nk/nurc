# PyInstaller spec: NURC生成ツールを単一の .exe にまとめる。
# ビルド: python -m PyInstaller nurc.spec
# 生成物: dist/NURC生成ツール.exe

# templates/ と config.yaml を同梱する(config は exe の隣にも置けば上書き優先)。
datas = [
    ("templates", "templates"),
    ("config.yaml", "."),
]

a = Analysis(
    ["gui.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["nurc_gen.sites.karal", "nurc_gen.sites.jara"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NURC生成ツール",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUIアプリなのでコンソール非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
