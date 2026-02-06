# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for building the syft CLI as a standalone binary.

Usage:
    cd cli
    uv sync --extra build
    uv run pyinstaller syft.spec

Output will be in dist/syft (or dist/syft.exe on Windows)
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Get the CLI source directory
cli_dir = Path(SPECPATH)
src_dir = cli_dir / "src"

# Hidden imports for syfthub-sdk modules (may use dynamic imports)
sdk_hidden_imports = [
    "syfthub_sdk",
    "syfthub_sdk._http",
    "syfthub_sdk._pagination",
    "syfthub_sdk.accounting",
    "syfthub_sdk.aggregators",
    "syfthub_sdk.auth",
    "syfthub_sdk.chat",
    "syfthub_sdk.client",
    "syfthub_sdk.exceptions",
    "syfthub_sdk.hub",
    "syfthub_sdk.models",
    "syfthub_sdk.my_endpoints",
    "syfthub_sdk.syftai",
    "syfthub_sdk.users",
]

# Hidden imports for CLI modules
cli_hidden_imports = [
    "syfthub_cli",
    "syfthub_cli.main",
    "syfthub_cli.config",
    "syfthub_cli.output",
    "syfthub_cli.completion",
    "syfthub_cli.update",
    "syfthub_cli.commands",
    "syfthub_cli.commands.auth",
    "syfthub_cli.commands.config_cmd",
    "syfthub_cli.commands.discovery",
    "syfthub_cli.commands.management",
    "syfthub_cli.commands.query",
    "syfthub_cli.commands.update_cmd",
    "syfthub_cli.commands.utils",
]

# Collect all submodules for packages with dynamic imports
# This is more robust than listing individual modules
collected_submodules = (
    collect_submodules("rich")
    + collect_submodules("typer")
    + collect_submodules("click")
    + collect_submodules("shellingham")
    + collect_submodules("httpx")
    + collect_submodules("httpcore")
    + collect_submodules("anyio")
    + collect_submodules("pydantic")
    + collect_submodules("pydantic_core")
)

# Additional hidden imports for dependencies
dependency_hidden_imports = [
    # HTTP/2 support
    "h11",
    "h2",
    "hpack",
    "sniffio",
    # SSL/TLS support
    "ssl",
    "certifi",
    # Encoding support
    "encodings",
    "encodings.idna",
    "encodings.utf_8",
    "encodings.ascii",
    # Standard library modules that might be dynamically imported
    "json",
    "pathlib",
    "datetime",
    "typing",
    "typing_extensions",
    "email.mime.text",
    "email.mime.multipart",
]

# Combine all hidden imports
hidden_imports = (
    sdk_hidden_imports
    + cli_hidden_imports
    + collected_submodules
    + dependency_hidden_imports
)

# Collect data files for packages that need them
datas = collect_data_files("certifi")

# Analysis configuration
a = Analysis(
    ["src/syfthub_cli/main.py"],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce binary size
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "torch",
        "tensorflow",
        "pytest",
        "mypy",
        "ruff",
        # Development tools
        "_pytest",
        "coverage",
        "black",
        "isort",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Create the PYZ archive
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Create the executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="syft",
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
