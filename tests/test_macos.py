import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import call, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("macos", ROOT / "setup/macos.py")
macos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macos)


class MacOSScheduleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="agent home café & ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.state = self.home / ".agent-home"
        self.state.mkdir()
        (self.state / "state.json").write_text("{}", encoding="utf-8")
        self.repo = self.home / "repo with spaces & café"
        self.plist = self.home / "Library/LaunchAgents" / f"{macos.LABEL}.plist"
        self.domain = "gui/123"
        self.service = f"{self.domain}/{macos.LABEL}"
        uid = patch.object(macos.os, "getuid", return_value=123, create=True)
        uid.start()
        self.addCleanup(uid.stop)
        repo = patch.object(macos, "REPO", self.repo)
        repo.start()
        self.addCleanup(repo.stop)
        environment = patch.dict(os.environ, {"PATH": "/opt/homebrew/bin:/usr/bin:/bin"})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("CODEX_HOME", None)

    def result(self, code=0):
        return subprocess.CompletedProcess([], code)

    def test_install_writes_plist_with_absolute_paths_and_environment(self):
        custom = self.home / "custom codex & café"
        with patch.dict(os.environ, {"CODEX_HOME": str(custom)}):
            with patch.object(macos, "launchctl", side_effect=[self.result(), self.result(113),
                                                              self.result(), self.result()]) as ctl:
                macos.schedule(self.home)
        definition = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(definition["Label"], macos.LABEL)
        self.assertEqual(definition["ProgramArguments"],
                         [sys.executable, str(self.repo / "agent_home.py"), "sync"])
        self.assertEqual(definition["StartInterval"], 900)
        self.assertTrue(definition["RunAtLoad"])
        self.assertEqual(definition["EnvironmentVariables"], {
            "PATH": "/opt/homebrew/bin:/usr/bin:/bin", "CODEX_HOME": str(custom),
            "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never",
            "PYTHONIOENCODING": "utf-8",
        })
        self.assertEqual(definition["StandardOutPath"], str(self.state / "sync.log"))
        self.assertEqual(definition["StandardErrorPath"], str(self.state / "sync.log"))
        ctl.assert_has_calls([call("print", self.domain), call("print", self.service, check=False),
                              call("enable", self.service),
                              call("bootstrap", self.domain, str(self.plist))])

    def test_reinstall_unloads_registered_job_and_refreshes_configuration(self):
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(b"old configuration")
        with patch.object(macos, "launchctl", return_value=self.result()) as ctl:
            macos.schedule(self.home)
        self.assertEqual(ctl.call_args_list, [call("print", self.domain),
                         call("print", self.service, check=False), call("bootout", self.service),
                         call("enable", self.service), call("bootstrap", self.domain, str(self.plist))])
        self.assertNotIn("CODEX_HOME", plistlib.loads(self.plist.read_bytes())["EnvironmentVariables"])

    def test_remove_unloads_even_without_plist_and_is_repeatable(self):
        with patch.object(macos, "launchctl", return_value=self.result()) as ctl:
            macos.schedule(self.home, remove=True)
        ctl.assert_has_calls([call("print", self.service, check=False), call("bootout", self.service)])
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(b"old configuration")
        with patch.object(macos, "launchctl", return_value=self.result(113)) as ctl:
            macos.schedule(self.home, remove=True)
            macos.schedule(self.home, remove=True)
        self.assertFalse(self.plist.exists())
        self.assertTrue((self.state / "state.json").exists())
        self.assertEqual(ctl.call_args_list, [call("print", self.service, check=False)] * 2)

    def test_unload_failure_preserves_plist_and_propagates(self):
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(b"old configuration")
        failure = subprocess.CalledProcessError(1, ["launchctl", "bootout"], stderr="denied")
        with patch.object(macos, "launchctl", side_effect=[self.result(), failure]):
            with self.assertRaises(subprocess.CalledProcessError):
                macos.schedule(self.home, remove=True)
        self.assertEqual(self.plist.read_bytes(), b"old configuration")

    def test_missing_state_and_login_session_do_not_write_a_plist(self):
        (self.state / "state.json").unlink()
        with patch.object(macos, "launchctl") as ctl:
            with self.assertRaisesRegex(ValueError, "install first"):
                macos.schedule(self.home)
        ctl.assert_not_called()
        (self.state / "state.json").write_text("{}", encoding="utf-8")
        with patch.object(macos, "launchctl", side_effect=subprocess.CalledProcessError(1, "launchctl")):
            with self.assertRaises(subprocess.CalledProcessError):
                macos.schedule(self.home)
        self.assertFalse(self.plist.exists())

    def test_bootstrap_failure_is_propagated(self):
        failure = subprocess.CalledProcessError(5, ["launchctl", "bootstrap"])
        with patch.object(macos, "launchctl", side_effect=[self.result(), self.result(113),
                                                         self.result(), failure]):
            with self.assertRaises(subprocess.CalledProcessError):
                macos.schedule(self.home)


@unittest.skipUnless(sys.platform == "darwin", "Native macOS launchd")
class NativeLaunchdTests(unittest.TestCase):
    def test_install_run_reinstall_and_remove_isolated_agent(self):
        # Never load the real sync job or use the user's actual state/agent label.
        with tempfile.TemporaryDirectory(prefix="agent home café & ") as temporary:
            home = Path(temporary)
            state = home / ".agent-home"
            state.mkdir()
            (state / "state.json").write_text("{}", encoding="utf-8")
            repo = home / "repo with spaces"
            repo.mkdir()
            result = home / "result.json"
            probe = ("import json, os, pathlib, sys\n"
                     f"pathlib.Path({str(result)!r}).write_text(json.dumps({{\n"
                     "    'args': sys.argv[1:], 'codex': os.environ.get('CODEX_HOME'),\n"
                     "    'prompt': os.environ.get('GIT_TERMINAL_PROMPT'),\n"
                     "}), encoding='utf-8')\n")
            (repo / "agent_home.py").write_text(probe, encoding="utf-8")
            label = f"io.github.agent-home.test-{uuid.uuid4().hex}"
            with patch.object(macos, "REPO", repo), patch.object(macos, "LABEL", label):
                try:
                    for suffix in ("first", "second"):
                        result.unlink(missing_ok=True)
                        custom = str(home / suffix)
                        with patch.dict(os.environ, {"CODEX_HOME": custom}):
                            macos.schedule(home)
                        deadline = time.monotonic() + 20
                        while not result.exists() and time.monotonic() < deadline:
                            time.sleep(0.1)
                        self.assertTrue(result.exists(), "launchd did not execute the probe")
                        self.assertEqual(json.loads(result.read_text(encoding="utf-8")),
                                         {"args": ["sync"], "codex": custom, "prompt": "0"})
                finally:
                    macos.schedule(home, remove=True)
                macos.schedule(home, remove=True)
                service = f"gui/{os.getuid()}/{label}"
                self.assertNotEqual(macos.launchctl("print", service, check=False).returncode, 0)
                self.assertFalse((home / "Library/LaunchAgents" / f"{label}.plist").exists())


if __name__ == "__main__":
    unittest.main()
