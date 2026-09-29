# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Only embed the necessary files
datas = [
    ('instruction.txt', '.'),
    ('config/prompt_generator_config.json', 'config'),
    ('config/scene_schema.json', 'config'),
    ('web_gui/index.html', 'web_gui'),
    ('web_gui/style.css', 'web_gui'),
    ('web_gui/app.js', 'web_gui'),
    ('web_gui/picker.py', 'web_gui'),
]

# Hidden imports for Flask, docx, and standard modules
hiddenimports = [
    'flask',
    'jinja2',
    'werkzeug',
    'docx',
    'tkinter',
    'tkinter.filedialog',
    'prompt_generator',
    'prompt_generator.models',
    'prompt_generator.parser',
    'prompt_generator.config',
    'prompt_generator.docx_exporter',
    'prompt_generator.queue',
    'prompt_generator.reconciliation',
    'prompt_generator.gui_worker',
    'prompt_generator.gui_account_manager',
    'prompt_generator.providers.base',
    'prompt_generator.providers.antigravity_cli',
]

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        'tests',
        '_pytest',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
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
    name='PromptGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
