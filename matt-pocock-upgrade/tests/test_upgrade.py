import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("upgrade", Path(__file__).parents[1] / "scripts/upgrade.py")
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.repo = self.root / "repo"
        self.source = self.repo / "skills/engineering/tdd"
        self.source.mkdir(parents=True)
        (self.source / "SKILL.md").write_text("upstream")
        self.target = self.home / ".agents/skills/tdd"
        self.lock = self.home / ".agents/.skill-lock.json"

    def run_install(self, **kwargs):
        up.execute(self.home, self.repo, "abc", **kwargs)

    def legacy(self):
        self.target.mkdir(parents=True)
        (self.target / "SKILL.md").write_text("local")
        up.write_json(self.lock, {"version": 3, "skills": {
            "tdd": {"source": up.SOURCE}, "missing": {"source": up.SOURCE},
            "foreign": {"source": "someone/else"},
        }})

    def test_install_link_and_byte_noop(self):
        self.run_install(names=["tdd"])
        link = self.home / ".claude/skills/tdd"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), self.target.resolve())
        state = self.home / ".agents/.matt-pocock-upgrade.json"
        before = (state.read_bytes(), state.stat().st_mtime_ns)
        self.run_install()
        self.assertEqual(before, (state.read_bytes(), state.stat().st_mtime_ns))
        self.assertEqual(len(list((state.parent / "matt-pocock-backups").iterdir())), 1)

    def test_update_keeps_old_content(self):
        self.run_install(names=["tdd"])
        (self.source / "SKILL.md").write_text("new")
        self.run_install()
        self.assertEqual((self.target / "SKILL.md").read_text(), "new")
        backups = self.home / ".agents/matt-pocock-backups"
        self.assertTrue(any(p.read_text() == "upstream" for p in backups.rglob("SKILL.md")))

    def test_local_edit_blocks_update(self):
        self.run_install(names=["tdd"])
        (self.target / "SKILL.md").write_text("custom")
        with self.assertRaises(up.UpgradeError):
            self.run_install()
        self.assertEqual((self.target / "SKILL.md").read_text(), "custom")

    def test_adopt_preserves_content_and_other_lock_records(self):
        self.legacy()
        self.run_install(adopt=True)
        self.assertEqual((self.target / "SKILL.md").read_text(), "local")
        self.assertEqual(set(json.loads(self.lock.read_text())["skills"]), {"missing", "foreign"})
        self.assertFalse((self.home / ".agents/skills/missing").exists())
        self.run_install()
        self.assertEqual((self.target / "SKILL.md").read_text(), "upstream")

    def test_dry_run_changes_no_installation(self):
        self.legacy()
        before = self.lock.read_bytes()
        self.run_install(adopt=True, dry_run=True)
        self.assertEqual(before, self.lock.read_bytes())
        self.assertFalse((self.home / ".agents/.matt-pocock-upgrade.json").exists())

    def test_foreign_path_preflight_prevents_partial_install(self):
        other = self.repo / "skills/engineering/aaa"
        other.mkdir()
        (other / "SKILL.md").write_text("new")
        self.target.mkdir(parents=True)
        (self.target / "SKILL.md").write_text("foreign")
        with self.assertRaises(up.UpgradeError):
            self.run_install(names=["aaa", "tdd"])
        self.assertFalse((self.target.parent / "aaa").exists())

    def test_foreign_claude_link_is_protected(self):
        link = self.home / ".claude/skills/tdd"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.root / "foreign")
        with self.assertRaises(up.UpgradeError):
            self.run_install(names=["tdd"])
        self.assertFalse(self.target.exists())

    def test_missing_upstream_is_preserved(self):
        self.run_install(names=["tdd"])
        self.source.rename(self.source.parent / "renamed")
        self.run_install()
        self.assertEqual((self.target / "SKILL.md").read_text(), "upstream")
        self.assertFalse((self.target.parent / "renamed").exists())

    def test_pending_blocks_next_run(self):
        self.run_install(names=["tdd"])
        up.write_json(self.home / ".agents/.matt-pocock-upgrade-pending.json", {})
        with self.assertRaises(up.UpgradeError):
            self.run_install()

    def test_interrupted_install_leaves_backup_and_pending(self):
        self.run_install(names=["tdd"])
        (self.source / "SKILL.md").write_text("new")
        original = Path.rename
        def fail_stage(path, dest):
            if path.name.startswith(".tdd-"):
                raise OSError("模拟交换中断")
            return original(path, dest)
        with patch.object(Path, "rename", fail_stage):
            with self.assertRaises(OSError):
                self.run_install()
        pending = self.home / ".agents/.matt-pocock-upgrade-pending.json"
        backup = Path(json.loads(pending.read_text())["backup"])
        self.assertEqual((backup / "tdd.original/SKILL.md").read_text(), "upstream")

    def test_source_symlink_rejected(self):
        (self.source / "outside").symlink_to(self.root)
        with self.assertRaises(up.UpgradeError):
            self.run_install(names=["tdd"])


class RepositoryTests(unittest.TestCase):
    def test_dirty_wrong_branch_and_foreign_origin(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
            git("init", "-b", "main")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "initial")
            git("remote", "add", "origin", up.URL)
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
            self.assertEqual(len(up.prepare_repo(repo, True)), 40)
            (repo / "local").write_text("change")
            with self.assertRaises(up.UpgradeError):
                up.prepare_repo(repo, True)
            git("add", "local")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "local")
            git("checkout", "-b", "feature")
            with self.assertRaises(up.UpgradeError):
                up.prepare_repo(repo, True)
            git("checkout", "main")
            git("remote", "set-url", "origin", "https://example.invalid/foreign.git")
            with self.assertRaises(up.UpgradeError):
                up.prepare_repo(repo, True)


if __name__ == "__main__":
    unittest.main()
