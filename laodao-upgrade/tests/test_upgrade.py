import importlib.util
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
            self.assertIn(("git", "fetch", "origin", "main"), commands)
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


if __name__ == "__main__":
    unittest.main()
