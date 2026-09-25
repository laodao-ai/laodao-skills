import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "upgrade.py"
SPEC = importlib.util.spec_from_file_location("claude_upgrade", SCRIPT)
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)


class PlatformKeyTest(unittest.TestCase):
    def test_mapping(self):
        cases = [
            (("Darwin", "arm64"), {}, "darwin-arm64"),
            (("Darwin", "x86_64"), {}, "darwin-x64"),
            (("Darwin", "x86_64"), {"rosetta": True}, "darwin-arm64"),
            (("Linux", "aarch64"), {}, "linux-arm64"),
            (("Linux", "x86_64"), {"musl": True}, "linux-x64-musl"),
            (("Windows", "AMD64"), {}, "win32-x64"),
            (("Windows", "ARM64"), {}, "win32-arm64"),
            (("MINGW64_NT-10.0", "x86_64"), {}, "win32-x64"),
        ]
        for args, kwargs, expected in cases:
            with self.subTest(args=args, kwargs=kwargs):
                self.assertEqual(upgrade.platform_key(*args, **kwargs), expected)

    def test_unsupported(self):
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.platform_key("Linux", "riscv64")
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.platform_key("FreeBSD", "x86_64")


class ManifestTest(unittest.TestCase):
    MANIFEST = {
        "version": "2.1.282",
        "platforms": {
            "darwin-arm64": {"binary": "claude", "checksum": "ABC", "size": 3},
            "win32-x64": {"binary": "claude.exe", "checksum": "def", "size": 4},
        },
    }

    def test_asset_url(self):
        asset = upgrade.asset_from_manifest(self.MANIFEST, "win32-x64")
        self.assertEqual(
            asset.url,
            "https://downloads.claude.ai/claude-code-releases/2.1.282/win32-x64/claude.exe",
        )
        self.assertEqual(upgrade.asset_from_manifest(self.MANIFEST, "darwin-arm64").checksum, "abc")

    def test_missing_platform(self):
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.asset_from_manifest(self.MANIFEST, "linux-x64")

    def test_parse_version(self):
        self.assertEqual(upgrade.parse_version("2.1.282 (Claude Code)\n"), "2.1.282")
        self.assertIsNone(upgrade.parse_version("garbage"))


class VerifyTest(unittest.TestCase):
    def test_checksum_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bin"
            path.write_bytes(b"hello")
            good = upgrade.Asset("1.0.0", "darwin-arm64", "claude",
                                 hashlib.sha256(b"hello").hexdigest(), 5)
            upgrade.verify(path, good)
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.verify(path, good._replace(size=6))
            with self.assertRaises(upgrade.UpgradeError):
                upgrade.verify(path, good._replace(checksum="0" * 64))


@unittest.skipIf(sys.platform == "win32", "symlink install is the macOS/Linux path")
class InstallUnixTest(unittest.TestCase):
    def test_install_and_relink(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions, link = upgrade.unix_paths(Path(tmp))
            versions.mkdir(parents=True)
            old = versions / "1.0.0"
            old.write_bytes(b"old")
            link.parent.mkdir(parents=True)
            os.symlink(old, link)

            partial = versions / "1.0.1.download"
            partial.write_bytes(b"new")
            final = upgrade.install_unix(partial, versions, link, "1.0.1")

            self.assertEqual(final, versions / "1.0.1")
            self.assertFalse(partial.exists())
            self.assertTrue(os.access(final, os.X_OK))
            self.assertEqual(Path(os.readlink(link)), final)
            self.assertTrue(old.exists(), "old versions are kept")

    def test_fresh_install_creates_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions, link = upgrade.unix_paths(Path(tmp))
            partial = Path(tmp) / "dl"
            partial.write_bytes(b"new")
            upgrade.install_unix(partial, versions, link, "1.0.1")
            self.assertEqual(link.read_bytes(), b"new")


class InstallWindowsTest(unittest.TestCase):
    def test_replace_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "claude.exe"
            target.write_bytes(b"old")
            (Path(tmp) / "claude.exe.old").write_bytes(b"older")
            partial = Path(tmp) / "claude-1.0.1.exe.download"
            partial.write_bytes(b"new")

            upgrade.install_windows(partial, target)

            self.assertEqual(target.read_bytes(), b"new")
            self.assertEqual((Path(tmp) / "claude.exe.old").read_bytes(), b"old")
            self.assertFalse(partial.exists())


if __name__ == "__main__":
    unittest.main()
