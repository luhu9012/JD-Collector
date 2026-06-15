# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('ui', 'ui'),
        ('core.py', '.'),
    ],
    hiddenimports=[
        'webview',
        'webview.platforms.cocoa',
        'DrissionPage',
        'DrissionPage.chromium_page',
        'openai',
        'dotenv',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JD Collector',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='JD Collector',
)

app = BUNDLE(
    coll,
    name='JD Collector.app',
    # icon='assets/icon.icns',
    bundle_identifier='com.grayson.jdcollector',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
        'CFBundleShortVersionString': '2.0.0',
        'CFBundleVersion': '2',
    },
)
