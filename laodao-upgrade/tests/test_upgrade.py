import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "upgrade.py"
SPEC = importlib.util.spec_from_file_location("laodao_upgrade", SCRIPT)
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)


class Result:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, command, cwd, capture=False, check=True):
        key = tuple(command)
        self.calls.append((key, Path(cwd), capture, check))
        response = self.responses.get(key, Result())
        if check and response.returncode != 0:
            raise upgrade.CommandError(command, response.returncode)
        return response


class FindRepoTests(unittest.TestCase):
    def test_finds_canonical_dot_skills_checkout(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            repo = home / ".skills" / "laodao-skills"
            (repo / ".git").mkdir(parents=True)
            (repo / "setup.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            found = upgrade.find_repo(home=home, cwd=home / "elsewhere")

            self.assertEqual(found, repo.resolve())

    def test_explicit_path_must_be_a_checkout(self):
        with tempfile.TemporaryDirectory() as raw:
            invalid = Path(raw) / "not-a-repo"
            invalid.mkdir()

            with self.assertRaisesRegex(upgrade.UpgradeError, "不是有效的 laodao-skills 仓库"):
                upgrade.find_repo(explicit_repo=invalid, home=Path(raw), cwd=Path(raw))


class UpgradeRepoTests(unittest.TestCase):
    def make_repo(self, root):
        repo = Path(root) / "laodao-skills"
        (repo / ".git").mkdir(parents=True)
        (repo / "setup.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        return repo

    def test_dirty_worktree_stops_before_network_or_setup(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = self.make_repo(raw)
            runner = FakeRunner({
                ("git", "status", "--porcelain"): Result(" M README.md\n"),
            })

            with self.assertRaisesRegex(upgrade.UpgradeError, "未提交改动"):
                upgrade.upgrade_repo(repo, runner=runner, bash_path="bash")

            self.assertEqual(
                [call[0] for call in runner.calls],
                [("git", "status", "--porcelain")],
            )

    def test_fast_forwards_then_configures_both_clients(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = self.make_repo(raw)
            runner = FakeRunner({
                ("git", "status", "--porcelain"): Result(""),
                ("git", "branch", "--show-current"): Result("main\n"),
                ("git", "rev-parse", "HEAD"): Result("old\n"),
                ("git", "rev-parse", "origin/main"): Result("new\n"),
                ("git", "merge-base", "--is-ancestor", "HEAD", "origin/main"): Result(returncode=0),
            })

            result = upgrade.upgrade_repo(repo, runner=runner, bash_path="bash")

            commands = [call[0] for call in runner.calls]
            self.assertIn(("git", "fetch", "origin", "main", "--tags"), commands)
            self.assertIn(("git", "merge", "--ff-only", "origin/main"), commands)
            self.assertEqual(commands[-1], ("bash", str((repo / "setup.sh").resolve())))
            self.assertEqual(result.before, "old")
            self.assertEqual(result.after, "new")
            self.assertTrue(result.updated)

    def test_diverged_history_stops_before_setup(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = self.make_repo(raw)
            runner = FakeRunner({
                ("git", "status", "--porcelain"): Result(""),
                ("git", "branch", "--show-current"): Result("main\n"),
                ("git", "rev-parse", "HEAD"): Result("local\n"),
                ("git", "rev-parse", "origin/main"): Result("remote\n"),
                ("git", "merge-base", "--is-ancestor", "HEAD", "origin/main"): Result(returncode=1),
            })

            with self.assertRaisesRegex(upgrade.UpgradeError, "无法快进"):
                upgrade.upgrade_repo(repo, runner=runner, bash_path="bash")

            self.assertNotIn(
                ("bash", str((repo / "setup.sh").resolve())),
                [call[0] for call in runner.calls],
            )


class UpgradeFetchesNewTagsTests(unittest.TestCase):
    """真 git：公开仓发第二版并打新 tag 后，升级要把新 tag 一起拉回来。"""

    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)

    def test_upgrade_brings_new_release_tag(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bare = root / "public.git"
            self._git(root, "init", "-q", "--bare", str(bare))
            # 裸仓 HEAD 默认指向 init.defaultBranch（可能是 master），clone 会检出空分支
            self._git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
            dev = root / "dev"
            dev.mkdir()
            self._git(dev, "init", "-q", "-b", "main")
            self._git(dev, "config", "user.email", "test@example.com")
            self._git(dev, "config", "user.name", "Test")
            (dev / "setup.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            self._git(dev, "add", "-A")
            self._git(dev, "commit", "-q", "-m", "v1")
            self._git(dev, "tag", "-a", "v2.0.0", "-m", "v2.0.0")
            self._git(dev, "push", "-q", str(bare), "main", "refs/tags/v2.0.0")

            user = root / "user"
            self._git(root, "clone", "-q", str(bare), str(user))

            (dev / "more.txt").write_text("x\n", encoding="utf-8")
            self._git(dev, "add", "-A")
            self._git(dev, "commit", "-q", "-m", "v2")
            self._git(dev, "tag", "-a", "v2.0.1", "-m", "v2.0.1")
            self._git(dev, "push", "-q", str(bare), "main", "refs/tags/v2.0.1")

            upgrade.upgrade_repo(user, bash_path="bash")

            self.assertEqual(upgrade._read_version(user), "v2.0.1")


class ReadVersionTests(unittest.TestCase):
    def _run_git(self, repo, *args):
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_tag_form_has_no_vv(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            self._run_git(repo, "init", "-q")
            self._run_git(repo, "config", "user.email", "test@example.com")
            self._run_git(repo, "config", "user.name", "Test")
            (repo / "f.txt").write_text("x", encoding="utf-8")
            self._run_git(repo, "add", "f.txt")
            self._run_git(repo, "commit", "-q", "-m", "init")
            self._run_git(repo, "tag", "v2.0.0")

            version = upgrade._read_version(repo)

            self.assertEqual(version, "v2.0.0")
            self.assertNotIn("vv", version)

    def test_describe_failure_returns_unknown(self):
        with tempfile.TemporaryDirectory() as raw:
            # Not a git repository at all → `git describe` exits non-zero.
            repo = Path(raw)

            version = upgrade._read_version(repo)

            self.assertEqual(version, "unknown")

    def test_git_not_on_path_returns_unknown(self):
        original_run = upgrade.subprocess.run

        def fake_run(*args, **kwargs):
            raise OSError(2, "No such file or directory: git")

        upgrade.subprocess.run = fake_run
        try:
            version = upgrade._read_version(Path("/does/not/matter"))
        finally:
            upgrade.subprocess.run = original_run

        self.assertEqual(version, "unknown")


if __name__ == "__main__":
    unittest.main()
