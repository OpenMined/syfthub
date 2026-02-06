"""Auto-update functionality for SyftHub CLI."""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import httpx

from syfthub_cli import __version__

# GitHub repository for releases
GITHUB_REPO = "OpenMined/syfthub"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"

# Cache settings
UPDATE_CHECK_FILE = Path.home() / ".syfthub" / ".update_check"
CHECK_INTERVAL_HOURS = 24  # Check for updates once per day


class VersionInfo(NamedTuple):
    """Version information from GitHub release."""

    version: str
    download_url: str
    release_url: str
    published_at: str


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string into comparable tuple.

    Args:
        version_str: Version string like "0.1.0" or "v0.1.0"

    Returns:
        Tuple of integers for comparison
    """
    # Strip 'v' prefix if present
    version_str = version_str.lstrip("v")

    # Handle pre-release versions (e.g., "0.1.0-beta.1")
    base_version = version_str.split("-")[0]

    try:
        return tuple(int(x) for x in base_version.split("."))
    except ValueError:
        return (0, 0, 0)


def is_newer_version(latest: str, current: str) -> bool:
    """Check if latest version is newer than current.

    Args:
        latest: Latest version string
        current: Current version string

    Returns:
        True if latest is newer than current
    """
    return parse_version(latest) > parse_version(current)


def get_platform_binary_name() -> str:
    """Get the binary name for the current platform.

    Returns:
        Binary filename like "syft-linux-x64" or "syft-darwin-arm64"
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map OS names
    os_map = {"linux": "linux", "darwin": "darwin", "windows": "windows"}
    os_name = os_map.get(system, system)

    # Map architectures
    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    arch = arch_map.get(machine, machine)

    if os_name == "windows":
        return f"syft-{os_name}-{arch}.exe"
    return f"syft-{os_name}-{arch}"


def get_latest_release() -> VersionInfo | None:
    """Fetch the latest CLI release from GitHub.

    Returns:
        VersionInfo if found, None otherwise
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(GITHUB_API_URL)
            response.raise_for_status()
            releases = response.json()

            # Find the latest CLI release (tag starts with "cli/v")
            for release in releases:
                tag = release.get("tag_name", "")
                if tag.startswith("cli/v"):
                    version = tag.replace("cli/v", "")
                    binary_name = get_platform_binary_name()

                    # Find the download URL for our platform
                    download_url = None
                    for asset in release.get("assets", []):
                        if asset.get("name") == binary_name:
                            download_url = asset.get("browser_download_url")
                            break

                    if download_url:
                        return VersionInfo(
                            version=version,
                            download_url=download_url,
                            release_url=release.get("html_url", ""),
                            published_at=release.get("published_at", ""),
                        )

            return None

    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return None


def load_update_cache() -> dict[str, str]:
    """Load cached update check data.

    Returns:
        Cached data dict or empty dict
    """
    if UPDATE_CHECK_FILE.exists():
        try:
            result: dict[str, str] = json.loads(UPDATE_CHECK_FILE.read_text())
            return result
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_update_cache(data: dict[str, str]) -> None:
    """Save update check data to cache.

    Args:
        data: Data to cache
    """
    try:
        UPDATE_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_CHECK_FILE.write_text(json.dumps(data))
    except OSError:
        pass  # Silently fail if we can't write cache


def should_check_for_updates() -> bool:
    """Check if we should perform an update check.

    Returns:
        True if enough time has passed since last check
    """
    cache = load_update_cache()
    last_check = cache.get("last_check")

    if not last_check:
        return True

    try:
        last_check_time = datetime.fromisoformat(last_check)
        # Make sure both are timezone-aware for comparison
        if last_check_time.tzinfo is None:
            last_check_time = last_check_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return now - last_check_time > timedelta(hours=CHECK_INTERVAL_HOURS)
    except ValueError:
        return True


def check_for_updates(force: bool = False) -> VersionInfo | None:
    """Check if a newer version is available.

    Args:
        force: If True, bypass cache and check immediately

    Returns:
        VersionInfo if update available, None otherwise
    """
    cache = load_update_cache()

    # Use cached result if recent enough and not forcing
    if not force and not should_check_for_updates():
        cached_version = cache.get("latest_version")
        if cached_version and is_newer_version(cached_version, __version__):
            return VersionInfo(
                version=cached_version,
                download_url=cache.get("download_url", ""),
                release_url=cache.get("release_url", ""),
                published_at=cache.get("published_at", ""),
            )
        return None

    # Fetch latest release
    latest = get_latest_release()

    # Update cache
    cache["last_check"] = datetime.now(timezone.utc).isoformat()
    if latest:
        cache["latest_version"] = latest.version
        cache["download_url"] = latest.download_url
        cache["release_url"] = latest.release_url
        cache["published_at"] = latest.published_at
    save_update_cache(cache)

    # Check if newer
    if latest and is_newer_version(latest.version, __version__):
        return latest

    return None


def get_current_executable() -> Path | None:
    """Get the path to the current executable.

    Returns:
        Path to executable if running as binary, None if running via Python
    """
    # sys.executable is the Python interpreter when running via `python -m` or pip
    # When running as PyInstaller binary, it's the binary itself
    executable = Path(sys.executable)

    # Check if we're running as a PyInstaller bundle
    if getattr(sys, "frozen", False):
        return executable

    # Check if we're running from an installed script
    # In this case, we might be able to find the syft binary
    if executable.name == "python" or executable.name.startswith("python"):
        # Running via Python interpreter - likely pip install
        return None

    return executable


def is_binary_install() -> bool:
    """Check if the CLI was installed as a standalone binary.

    Returns:
        True if running as standalone binary
    """
    return getattr(sys, "frozen", False)


def download_binary(url: str, dest: Path) -> bool:
    """Download binary from URL.

    Args:
        url: Download URL
        dest: Destination path

    Returns:
        True if download successful
    """
    try:
        with (
            httpx.Client(timeout=60.0, follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return True
    except (httpx.HTTPError, OSError):
        return False


def perform_self_update(version_info: VersionInfo) -> tuple[bool, str]:
    """Perform self-update to the specified version.

    Args:
        version_info: Version information with download URL

    Returns:
        Tuple of (success, message)
    """
    if not is_binary_install():
        return False, (
            "Self-update is only available for standalone binary installations.\n"
            "Please update using pip: pip install --upgrade syfthub-cli\n"
            "Or reinstall using the install script."
        )

    current_exe = get_current_executable()
    if not current_exe:
        return False, "Could not determine current executable path."

    # Create temp directory for download
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        new_binary = tmp_path / "syft_new"

        # Download new binary
        if not download_binary(version_info.download_url, new_binary):
            return False, "Failed to download new version."

        # Make executable
        new_binary.chmod(new_binary.stat().st_mode | stat.S_IEXEC)

        # Verify new binary works
        try:
            result = subprocess.run(
                [str(new_binary), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False, "Downloaded binary verification failed."
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"Binary verification error: {e}"

        # Replace current binary
        try:
            # On Windows, we can't replace a running executable directly
            if platform.system() == "Windows":
                # Rename current to .old, copy new, delete old on next run
                old_exe = current_exe.with_suffix(".old")
                if old_exe.exists():
                    old_exe.unlink()
                current_exe.rename(old_exe)
                shutil.copy2(new_binary, current_exe)
            else:
                # On Unix, we can replace the binary
                # First try direct copy (works if we have write permission)
                try:
                    shutil.copy2(new_binary, current_exe)
                except PermissionError:
                    # Try with sudo
                    result = subprocess.run(
                        ["sudo", "cp", str(new_binary), str(current_exe)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        return False, (
                            "Permission denied. Try running with sudo:\n"
                            "  sudo syft update"
                        )

        except OSError as e:
            return False, f"Failed to replace binary: {e}"

    # Clear update cache
    cache = load_update_cache()
    cache["latest_version"] = version_info.version
    cache["last_check"] = datetime.now(timezone.utc).isoformat()
    save_update_cache(cache)

    return True, f"Successfully updated to v{version_info.version}!"


def get_update_notification() -> str | None:
    """Get update notification message if update is available.

    This is called on every CLI invocation but uses caching to avoid
    excessive API calls.

    Returns:
        Notification message or None
    """
    # Don't check if disabled via environment variable
    if os.environ.get("SYFT_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes"):
        return None

    update = check_for_updates(force=False)
    if update:
        return (
            f"\n[yellow]A new version of syft is available: "
            f"v{__version__} -> v{update.version}[/yellow]\n"
            f"[dim]Run 'syft update' to update, or visit {update.release_url}[/dim]"
        )

    return None
