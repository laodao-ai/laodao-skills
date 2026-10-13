#!/usr/bin/env python3
"""Upgrade the Claude Code native binary without the official install script.

Flow: latest version -> manifest.json -> download with curl (retry + resume)
-> sha256 check -> install.
  - macOS / Linux: ~/.local/share/claude/versions/<version>, chmod +x,
    symlink ~/.local/bin/claude -> that file.
  - Windows: replace the existing claude.exe in place.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple, Optional

BASE_URL = "https://downloads.claude.ai/claude-code-releases"
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
DOWNLOAD_ATTEMPTS = 5


class UpgradeError(RuntimeError):
    """Raised when the upgrade cannot continue safely."""


class Asset(NamedTuple):
    version: str
    platform: str
    binary: str
    checksum: str
    size: int

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.version}/{self.platform}/{self.binary}"


# ─── platform ─────────────────────────────────────────────


def _is_rosetta() -> bool:
    # An x64 Python under Rosetta reports x86_64; the arm64 build is the right one.
    try:
        out = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except OSError:
        return False
    return out == "1"


def _is_musl() -> bool:
    return bool(glob.glob("/lib/libc.musl-*.so.1") or glob.glob("/lib/ld-musl-*.so.1"))


def platform_key(system: str, machine: str, rosetta: bool = False, musl: bool = False) -> str:
    """Map OS/arch to the manifest's platform key, e.g. darwin-arm64, win32-x64."""
    machine = machine.lower()
    if machine in ("x86_64", "amd64", "x64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise UpgradeError(f"不支持的 CPU 架构：{machine}")

    system = system.lower()
    if system == "darwin":
        if arch == "x64" and rosetta:
            arch = "arm64"
        return f"darwin-{arch}"
    if system == "linux":
        return f"linux-{arch}-musl" if musl else f"linux-{arch}"
    if system == "windows" or system.startswith(("mingw", "msys", "cygwin")):
        return f"win32-{arch}"
    raise UpgradeError(f"不支持的操作系统：{system}")


def detect_platform() -> str:
    system = platform.system()
    return platform_key(
        system,
        platform.machine(),
        rosetta=system == "Darwin" and _is_rosetta(),
        musl=system == "Linux" and _is_musl(),
    )


def is_windows_platform(key: str) -> bool:
    return key.startswith("win32-")


# ─── network ──────────────────────────────────────────────


def _curl() -> str:
    exe = shutil.which("curl")
    if not exe:
        raise UpgradeError("找不到 curl。macOS/Linux 请安装 curl；Windows 10 1803+ 自带 curl.exe。")
    return exe


def fetch_text(url: str) -> str:
    # curl honours HTTPS_PROXY / HTTP_PROXY, same as the user's shell.
    proc = subprocess.run(
        [_curl(), "-fsSL", "--retry", "3", "--retry-delay", "2", "--connect-timeout", "20", url],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise UpgradeError(f"请求失败（curl exit {proc.returncode}）：{url}\n{proc.stderr.strip()}")
    return proc.stdout


def parse_version(text: str) -> Optional[str]:
    match = VERSION_RE.search(text)
    return match.group(0) if match else None


def latest_version() -> str:
    text = fetch_text(f"{BASE_URL}/latest").strip()
    if not VERSION_RE.fullmatch(text):
        raise UpgradeError(f"latest 返回的不是版本号：{text[:200]!r}")
    return text


def asset_from_manifest(manifest: dict, key: str) -> Asset:
    entry = manifest.get("platforms", {}).get(key)
    if not entry:
        raise UpgradeError(f"manifest 中没有平台 {key}")
    return Asset(
        version=manifest["version"],
        platform=key,
        binary=entry["binary"],
        checksum=entry["checksum"].lower(),
        size=int(entry["size"]),
    )


def fetch_asset(version: str, key: str) -> Asset:
    text = fetch_text(f"{BASE_URL}/{version}/manifest.json")
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UpgradeError(f"manifest.json 解析失败：{exc}") from exc
    return asset_from_manifest(manifest, key)


def download(asset: Asset, dest: Path) -> None:
    """Download to dest; each retry resumes from the partial file (-C -)."""
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        print(f"下载 {asset.url}（第 {attempt}/{DOWNLOAD_ATTEMPTS} 次）", flush=True)
        proc = subprocess.run(
            [_curl(), "-fL", "-#", "-C", "-", "--retry", "3", "--retry-delay", "2",
             "--connect-timeout", "20", "-o", str(dest), asset.url],
            check=False,
        )
        if proc.returncode == 0 and dest.stat().st_size >= asset.size:
            return
        # 416 = range not satisfiable: the partial file is already complete or corrupt.
        if dest.exists() and dest.stat().st_size >= asset.size:
            return
        time.sleep(2)
    raise UpgradeError(f"下载 {DOWNLOAD_ATTEMPTS} 次仍未完成：{asset.url}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, asset: Asset) -> None:
    size = path.stat().st_size
    if size != asset.size:
        raise UpgradeError(f"文件大小不符：期望 {asset.size}，实际 {size}（{path}）")
    actual = sha256_of(path)
    if actual != asset.checksum:
        raise UpgradeError(f"sha256 不符：期望 {asset.checksum}，实际 {actual}（{path}）")


# ─── install ──────────────────────────────────────────────


def unix_paths(home: Path) -> tuple[Path, Path]:
    return home / ".local" / "share" / "claude" / "versions", home / ".local" / "bin" / "claude"


def windows_target(home: Path) -> Path:
    found = shutil.which("claude")
    if found and found.lower().endswith(".exe"):
        return Path(found)
    return home / ".local" / "bin" / "claude.exe"


def install_unix(downloaded: Path, versions_dir: Path, link: Path, version: str) -> Path:
    """Move the verified binary to versions/<version> and point the symlink at it."""
    versions_dir.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)

    final = versions_dir / version
    os.chmod(downloaded, 0o755)
    os.replace(downloaded, final)

    # Build the new link beside the old one, then rename over it: never a moment without `claude`.
    tmp_link = link.with_name(link.name + ".tmp-link")
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()
    os.symlink(final, tmp_link)
    os.replace(tmp_link, link)
    return final


def install_windows(downloaded: Path, target: Path) -> Path:
    """Replace target claude.exe. A running exe can be renamed but not overwritten,
    so the old one is moved aside to claude.exe.old first."""
    backup = target.with_name(target.name + ".old")
    if target.exists():
        if backup.exists():
            try:
                backup.unlink()
            except OSError:
                # The previous .old may still be running; pick a fresh name.
                backup = target.with_name(f"{target.name}.old-{int(time.time())}")
        os.replace(target, backup)
    try:
        os.replace(downloaded, target)
    except OSError:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    return target


def installed_version(executable: Path) -> Optional[str]:
    if not executable.exists():
        return None
    try:
        proc = subprocess.run(
            [str(executable), "--version"], capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_version(proc.stdout)


# ─── main ─────────────────────────────────────────────────


def run(version: Optional[str], check_only: bool, force: bool) -> int:
    key = detect_platform()
    home = Path.home()
    windows = is_windows_platform(key)

    if windows:
        executable = windows_target(home)
    else:
        versions_dir, executable = unix_paths(home)

    target_version = version or latest_version()
    current = installed_version(executable)
    print(f"平台：{key}")
    print(f"安装位置：{executable}")
    print(f"当前版本：{current or '未安装/无法识别'}")
    print(f"目标版本：{target_version}")

    if check_only:
        print("已是目标版本。" if current == target_version else "与目标版本不同，可升级。")
        return 0
    if current == target_version and not force:
        print("已是目标版本，无需升级（加 --force 可强制重装）。")
        return 0

    asset = fetch_asset(target_version, key)

    if windows:
        if not executable.parent.exists():
            raise UpgradeError(f"目录不存在：{executable.parent}")
        partial = executable.with_name(f"claude-{asset.version}.exe.download")
    else:
        versions_dir.mkdir(parents=True, exist_ok=True)
        partial = versions_dir / f"{asset.version}.download"

    download(asset, partial)
    try:
        verify(partial, asset)
    except UpgradeError:
        partial.unlink(missing_ok=True)
        raise
    print("sha256 校验通过。")

    if windows:
        install_windows(partial, executable)
    else:
        final = install_unix(partial, versions_dir, executable, asset.version)
        print(f"已写入 {final}")

    after = installed_version(executable)
    if after != asset.version:
        raise UpgradeError(f"安装后 `{executable} --version` 为 {after!r}，期望 {asset.version}")
    print(f"升级完成：{current or '无'} -> {after}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="下载并安装 Claude Code 原生二进制")
    parser.add_argument("--version", help="安装指定版本（默认取 latest）")
    parser.add_argument("--check", action="store_true", help="只比较版本，不下载")
    parser.add_argument("--force", action="store_true", help="版本相同也重装")
    args = parser.parse_args(argv)
    try:
        return run(args.version, args.check, args.force)
    except UpgradeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
