# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for LitRadar Django backend."""

block_cipher = None

a = Analysis(
    ['run_django.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'django',
        'django.core.management',
        'django.core.management.commands.runserver',
        'django.core.management.commands.migrate',
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'rest_framework',
        'corsheaders',
        'apps.core',
        'apps.core.models',
        'apps.core.urls',
        'apps.core.views',
        'litradar',
        'litradar.settings',
        'litradar.urls',
        'litradar.wsgi',
        'sqlite3',
        'json',
        'urllib',
        'ssl',
        'xml.etree.ElementTree',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='litradar-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
