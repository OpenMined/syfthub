#!/usr/bin/env python3
"""Build script for creating standalone syft CLI binaries.

This script:
1. Detects the current platform and architecture
2. Runs PyInstaller with the syft.spec configuration
3. Renames the output binary with platform/arch suffix
4. Verifies the built binary works

Usage:
    cd cli
    uv sync --extra build
    uv run python scripts/build.py

Or with options:
    uv run python scripts/build.py --output-dir ./release --skip-verify
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_platform_info() -> tuple[str, str]:
    """Get the current platform and architecture.

    Returns:
        Tuple of (os_name, arch) like ('linux', 'x64') or ('darwin', 'arm64')
    """
    system = platform.system().lower()

    # Normalize OS name
    os_map = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "windows",
    }
    os_name = os_map.get(system, system)

    # Get architecture
    machine = platform.machine().lower()
    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "arm",
        "i386": "x86",
        "i686": "x86",
    }
    arch = arch_map.get(machine, machine)

    return os_name, arch


def get_binary_name(os_name: str, arch: str) -> str:
    """Get the output binary name with platform suffix.

    Args:
        os_name: Operating system name (linux, darwin, windows)
        arch: Architecture (x64, arm64, etc.)

    Returns:
        Binary name like 'syft-linux-x64' or 'syft-windows-x64.exe'
    """
    base_name = f"syft-{os_name}-{arch}"
    if os_name == "windows":
        return f"{base_name}.exe"
    return base_name


def run_pyinstaller(spec_file: Path, work_dir: Path) -> Path:
    """Run PyInstaller to build the binary.

    Args:
        spec_file: Path to the .spec file
        work_dir: Working directory (cli directory)

    Returns:
        Path to the built binary

    Raises:
        subprocess.CalledProcessError: If PyInstaller fails
    """
    print(f"Running PyInstaller with {spec_file}...")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ]

    subprocess.run(cmd, cwd=work_dir, check=True)

    # Determine output path
    os_name, _ = get_platform_info()
    if os_name == "windows":
        output_path = work_dir / "dist" / "syft.exe"
    else:
        output_path = work_dir / "dist" / "syft"

    if not output_path.exists():
        raise FileNotFoundError(f"Expected binary not found: {output_path}")

    return output_path


def verify_binary(binary_path: Path) -> bool:
    """Verify the built binary works.

    Args:
        binary_path: Path to the binary to verify

    Returns:
        True if verification passes, False otherwise
    """
    print(f"Verifying binary: {binary_path}")

    # Test --version
    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"Version check failed: {result.stderr}")
            return False
        print(f"Version: {result.stdout.strip()}")
    except subprocess.TimeoutExpired:
        print("Version check timed out")
        return False
    except Exception as e:
        print(f"Version check error: {e}")
        return False

    # Test --help
    try:
        result = subprocess.run(
            [str(binary_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"Help check failed: {result.stderr}")
            return False
        print("Help command: OK")
    except subprocess.TimeoutExpired:
        print("Help check timed out")
        return False
    except Exception as e:
        print(f"Help check error: {e}")
        return False

    # Test config show
    try:
        result = subprocess.run(
            [str(binary_path), "config", "show"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Config show might fail if not configured, but shouldn't crash
        print("Config show command: OK")
    except subprocess.TimeoutExpired:
        print("Config show timed out")
        return False
    except Exception as e:
        print(f"Config show error: {e}")
        return False

    return True


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA256 checksum
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def main() -> int:
    """Main entry point for the build script."""
    parser = argparse.ArgumentParser(
        description="Build standalone syft CLI binary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for the final binary (default: cli/dist)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip binary verification step",
    )
    parser.add_argument(
        "--checksum",
        action="store_true",
        help="Generate SHA256 checksum file",
    )

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    cli_dir = script_dir.parent
    spec_file = cli_dir / "syft.spec"

    if not spec_file.exists():
        print(f"Error: Spec file not found: {spec_file}")
        return 1

    # Get platform info
    os_name, arch = get_platform_info()
    print(f"Building for: {os_name}-{arch}")

    # Run PyInstaller
    try:
        built_binary = run_pyinstaller(spec_file, cli_dir)
    except subprocess.CalledProcessError as e:
        print(f"PyInstaller failed with exit code {e.returncode}")
        return 1
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    # Get file size
    size_mb = built_binary.stat().st_size / (1024 * 1024)
    print(f"Binary size: {size_mb:.1f} MB")

    # Verify binary
    if not args.skip_verify:
        if not verify_binary(built_binary):
            print("Binary verification failed!")
            return 1
        print("Binary verification passed!")

    # Rename with platform suffix
    final_name = get_binary_name(os_name, arch)
    output_dir = args.output_dir or (cli_dir / "dist")
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / final_name

    if final_path != built_binary:
        shutil.copy2(built_binary, final_path)
        print(f"Binary copied to: {final_path}")
    else:
        # Rename in place
        final_path = built_binary.parent / final_name
        built_binary.rename(final_path)
        print(f"Binary renamed to: {final_path}")

    # Generate checksum
    if args.checksum:
        checksum = calculate_checksum(final_path)
        checksum_file = final_path.with_suffix(final_path.suffix + ".sha256")
        checksum_file.write_text(f"{checksum}  {final_name}\n")
        print(f"Checksum written to: {checksum_file}")
        print(f"SHA256: {checksum}")

    print(f"\nBuild successful: {final_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
