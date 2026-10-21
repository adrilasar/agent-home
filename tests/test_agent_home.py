import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "agent_home.py"
spec = importlib.util.spec_from_file_location("agent_home", SCRIPT)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent home ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "user home"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.patch_repo = patch.object(app, "REPO", self.repo)
        self.patch_repo.start()
        self.addCleanup(self.patch_repo.stop)
        self.patch_env = patch.dict(os.environ)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        schedule_patch = patch.object(app, "schedule")
        self.scheduler = schedule_patch.start()
        self.addCleanup(schedule_patch.stop)
        os.environ.pop("CODEX_HOME", None)
        self.put("common/FRAGMENT.md", "shared café")
        self.put("harnesses/codex/FRAGMENT.md", "codex-only")
        self.put("machines/desktop/FRAGMENT.md", "desktop-only")
        self.put("machines/desktop/harnesses/codex/FRAGMENT.md", "desktop-and-codex")
        self.put("machines/laptop/FRAGMENT.md", "laptop-only")
        self.skill("common", "global")
        self.skill("machines/desktop", "local")

    def put(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def skill(self, scope, name):
        return self.put(f"{scope}/skills/{name}/SKILL.md", f"---\nname: {name}\ndescription: Example\n---\n")

    def install(self):
        app.apply(self.home, "desktop", ["codex"])

    def test_scope_composition_and_harness_isolation(self):
        app.apply(self.home, "desktop", ["codex", "claude"])
        codex = (self.home / ".codex/AGENTS.md").read_text(encoding="utf-8")
        claude = (self.home / ".claude/CLAUDE.md").read_text(encoding="utf-8")
        for text in (codex, claude):
            self.assertIn("shared café", text)
            self.assertIn("desktop-only", text)
            self.assertNotIn("laptop-only", text)
        self.assertIn("codex-only", codex)
        self.assertIn("desktop-and-codex", codex)
        self.assertNotIn("codex-only", claude)
        self.assertNotIn("desktop-and-codex", claude)
        app.apply(self.home, "laptop", ["codex"])
        self.assertFalse((self.home / ".codex/skills/local/SKILL.md").exists())
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())
        self.assertTrue((self.home / ".codex/skills/global/SKILL.md").exists())

    def test_initial_backups_idempotence_and_non_destructive_uninstall(self):
        original = self.home / ".codex/AGENTS.md"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"original instructions\r\n")
        legacy_skill = self.home / ".codex/skills/global/SKILL.md"
        legacy_skill.parent.mkdir(parents=True)
        legacy_skill.write_bytes(b"original skill")
        unrelated = self.home / ".codex/skills/unmanaged/SKILL.md"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_bytes(b"leave unchanged")
        self.install()
        backups = self.home / ".agent-home/backups"
        self.assertEqual((backups / app.digest(str(original).encode())).read_bytes(), b"original instructions\r\n")
        self.assertEqual((backups / app.digest(str(legacy_skill).encode())).read_bytes(), b"original skill")
        backup_times = {p.name: p.stat().st_mtime_ns for p in backups.iterdir()}
        first_state = app.load_state(self.home)
        self.install()
        self.assertEqual(first_state, app.load_state(self.home))
        self.assertEqual(backup_times, {p.name: p.stat().st_mtime_ns for p in backups.iterdir()})
        original.write_bytes(b"keep this local edit")
        installed = {p: p.read_bytes() for p in (self.home / ".codex").rglob("*") if p.is_file()}
        app.uninstall(self.home)
        self.assertEqual(installed, {p: p.read_bytes() for p in (self.home / ".codex").rglob("*") if p.is_file()})
        self.assertFalse((self.home / ".agent-home").exists())
        self.scheduler.assert_called_once_with(remove=True)
        app.uninstall(self.home)

    def test_local_edit_blocks_all_updates(self):
        self.install()
        changed = self.home / ".codex/skills/global/SKILL.md"
        changed.write_bytes("my café edit".encode())
        original_instructions = (self.home / ".codex/AGENTS.md").read_bytes()
        self.put("common/FRAGMENT.md", "new instructions")
        with self.assertRaisesRegex(ValueError, "Local edit"):
            self.install()
        self.assertEqual((self.home / ".codex/AGENTS.md").read_bytes(), original_instructions)
        self.assertEqual(changed.read_bytes(), "my café edit".encode())

    def test_scheduler_failure_preserves_state_and_backups_on_uninstall(self):
        original = self.home / ".codex/AGENTS.md"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"original")
        self.install()
        state_root = self.home / ".agent-home"
        before = {p: p.read_bytes() for p in state_root.rglob("*") if p.is_file()}
        self.scheduler.side_effect = subprocess.CalledProcessError(1, "scheduler")
        with self.assertRaises(subprocess.CalledProcessError):
            app.uninstall(self.home)
        self.assertEqual(before, {p: p.read_bytes() for p in state_root.rglob("*") if p.is_file()})

    def test_new_and_removed_skills_and_unmanaged_files(self):
        original = self.home / ".codex/skills/global/SKILL.md"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"skill predating agent-home")
        self.install()
        extra = self.home / ".codex/skills/global/own.txt"
        extra.write_bytes(b"local")
        shutil.rmtree(self.repo / "common/skills/global")
        self.skill("common", "new")
        self.install()
        self.assertFalse((self.home / ".codex/skills/global/SKILL.md").exists())
        self.assertTrue((self.home / ".codex/skills/new/SKILL.md").exists())
        self.assertEqual(extra.read_bytes(), b"local")
        self.assertEqual((self.home / ".agent-home/backups" / app.digest(str(original).encode())).read_bytes(),
                         b"skill predating agent-home")

    def test_collision_is_rejected_before_writing(self):
        self.skill("machines/desktop", "global")
        with self.assertRaisesRegex(ValueError, "Duplicate skill"):
            self.install()
        self.assertFalse(self.home.exists())

    def test_backups_expire_after_seven_days_without_being_recreated(self):
        original = self.home / ".codex/AGENTS.md"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"original")
        self.install()
        backup = next((self.home / ".agent-home/backups").iterdir())
        created = backup.stat().st_mtime
        with patch.object(app.time, "time", return_value=created + 7 * 86400 - 1):
            self.install()
            self.assertTrue(backup.exists())
        with patch.object(app.time, "time", return_value=created + 7 * 86400):
            with patch.object(app, "git", side_effect=OSError("offline")):
                with self.assertRaisesRegex(OSError, "offline"):
                    app.sync(self.home)
            self.assertFalse(backup.exists())
        self.install()
        self.assertEqual(list((self.home / ".agent-home/backups").iterdir()), [])
        self.assertTrue(original.is_file())

    def test_cli_installs_and_removes_scheduling(self):
        with patch.object(Path, "home", return_value=self.home):
            with patch.object(sys, "argv", ["agent_home.py", "install", "desktop", "codex"]):
                app.main()
            self.scheduler.assert_called_once_with()
            self.assertTrue((self.home / ".codex/AGENTS.md").exists())
            with patch.object(sys, "argv", ["agent_home.py", "uninstall"]):
                app.main()
            self.scheduler.assert_called_with(remove=True)
        self.assertTrue((self.home / ".codex/AGENTS.md").exists())
        self.assertFalse((self.home / ".agent-home").exists())

    def test_custom_codex_home(self):
        custom = self.root / "codex custom"
        with patch.dict(os.environ, {"CODEX_HOME": str(custom)}):
            self.install()
        self.assertTrue((custom / "AGENTS.md").exists())
        app.uninstall(self.home)
        self.assertTrue((custom / "AGENTS.md").exists())


class ScheduleTests(unittest.TestCase):
    def test_platform_dispatch_for_install_and_remove(self):
        for name, platform, command, removal in (
                ("posix", "darwin", [sys.executable, str(app.REPO / "setup/macos.py")], "remove"),
                ("posix", "linux", ["bash", str(app.REPO / "setup/linux.sh")], "remove"),
                ("nt", "win32", ["powershell.exe", "-NoProfile", "-File",
                                  str(app.REPO / "setup/windows.ps1")], "-Remove")):
            for remove in (False, True):
                with self.subTest(platform=platform, remove=remove):
                    with patch.object(app.os, "name", name), patch.object(app.sys, "platform", platform):
                        with patch.object(app.subprocess, "run") as run:
                            app.schedule(remove=remove)
                    run.assert_called_once_with(command + ([removal] if remove else []), check=True)


class SyncTests(unittest.TestCase):
    def test_upstream_update_preserves_private_content(self):
        with tempfile.TemporaryDirectory(prefix="agent upstream ") as temporary:
            root = Path(temporary).resolve()
            upstream = root / "public"
            private = root / "private"
            home = root / "home"
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
            env.pop("CODEX_HOME", None)

            def git(cwd, *args):
                return subprocess.run(["git", "-C", str(cwd), *args], env=env,
                                      check=True, capture_output=True, text=True)

            git(root, "init", "--initial-branch=main", str(upstream))
            git(upstream, "config", "user.name", "Test")
            git(upstream, "config", "user.email", "test@example.invalid")
            shutil.copy2(SCRIPT, upstream / "agent_home.py")
            git(upstream, "add", ".")
            git(upstream, "commit", "-m", "Public base")
            git(root, "clone", str(upstream), str(private))
            git(private, "remote", "rename", "origin", "upstream")
            git(private, "config", "user.name", "Test")
            git(private, "config", "user.email", "test@example.invalid")
            personal = private / "machines/desktop/FRAGMENT.md"
            personal.parent.mkdir(parents=True)
            personal.write_text("Private instructions", encoding="utf-8")
            git(private, "add", ".")
            git(private, "commit", "-m", "Personal content")
            public_skill = upstream / "common/skills/shared/SKILL.md"
            public_skill.parent.mkdir(parents=True)
            public_skill.write_text("Public skill update", encoding="utf-8")
            git(upstream, "add", ".")
            git(upstream, "commit", "-m", "Add shared skill")
            git(private, "fetch", "upstream")
            git(private, "merge", "--no-edit", "upstream/main")

            with patch.object(app, "REPO", private), patch.dict(os.environ, env):
                app.apply(home, "desktop", ["codex"])
            self.assertIn("Private instructions", (home / ".codex/AGENTS.md").read_text())
            self.assertEqual((home / ".codex/skills/shared/SKILL.md").read_text(),
                             "Public skill update")
            self.assertFalse((upstream / "machines/desktop").exists())

    def test_real_git_update_dirty_tree_and_unpublished_commits(self):
        with tempfile.TemporaryDirectory(prefix="agent sync ") as temporary:
            root = Path(temporary).resolve()
            remote = root / "remote.git"
            author = root / "author"
            consumer = root / "consumer"
            home = root / "home"
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
            env.pop("CODEX_HOME", None)

            def git(cwd, *args):
                return subprocess.run(["git", "-C", str(cwd), *args], env=env,
                                      check=True, capture_output=True, text=True)

            git(root, "init", "--bare", "--initial-branch=main", str(remote))
            git(root, "clone", str(remote), str(author))
            git(author, "config", "user.name", "Test")
            git(author, "config", "user.email", "test@example.invalid")
            shutil.copy2(SCRIPT, author / "agent_home.py")
            (author / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
            (author / "machines/desktop").mkdir(parents=True)
            source = author / "machines/desktop/FRAGMENT.md"
            source.write_text("before", encoding="utf-8")
            git(author, "add", ".")
            git(author, "commit", "-m", "Initial")
            git(author, "push", "-u", "origin", "main")
            git(root, "clone", str(remote), str(consumer))
            with patch.object(app, "REPO", consumer), patch.dict(os.environ, env):
                app.apply(home, "desktop", ["codex"])
                source.write_text("after café", encoding="utf-8")
                git(author, "add", ".")
                git(author, "commit", "-m", "Update")
                git(author, "push")
                app.sync(home)
                installed = home / ".codex/AGENTS.md"
                self.assertIn("after café", installed.read_text(encoding="utf-8"))
                current = installed.read_bytes()
                git(consumer, "switch", "-c", "older", "HEAD~1")
                git(consumer, "push", "-u", "origin", "older")
                with self.assertRaisesRegex(ValueError, "Sync requires main"):
                    app.sync(home)
                self.assertEqual(installed.read_bytes(), current)
                git(consumer, "switch", "main")
                (consumer / "local.txt").write_text("unpublished", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "local changes"):
                    app.sync(home)
                git(consumer, "config", "user.name", "Test")
                git(consumer, "config", "user.email", "test@example.invalid")
                git(consumer, "add", ".")
                git(consumer, "commit", "-m", "Local only")
                with self.assertRaisesRegex(ValueError, "unpublished commits"):
                    app.sync(home)
                self.assertEqual(installed.read_bytes(), current)


if __name__ == "__main__":
    unittest.main()
