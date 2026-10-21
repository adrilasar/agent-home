import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / "setup/windows_sync.pyw"
PROBE = '''import ctypes, json
from ctypes import wintypes
ctypes.windll.kernel32.GetConsoleWindow.restype = wintypes.HWND
ctypes.windll.user32.IsWindowVisible.argtypes = [wintypes.HWND]
window = ctypes.windll.kernel32.GetConsoleWindow()
print(json.dumps({"console": bool(window), "visible": bool(ctypes.windll.user32.IsWindowVisible(window))}))
'''


@unittest.skipUnless(os.name == "nt", "Windows launcher")
class WindowsSyncTests(unittest.TestCase):
    def run_launcher(self, source, *, state=True):
        temporary = tempfile.TemporaryDirectory(prefix="agent home background ")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        launcher = root / "windows_sync.pyw"
        shutil.copy2(LAUNCHER, launcher)
        repo = root / "repo with spaces"
        repo.mkdir()
        (repo / "agent_home.py").write_text(source, encoding="utf-8")
        if state:
            (root / "state.json").write_text(json.dumps({"repo": str(repo)}), encoding="utf-8")
        result = subprocess.run([str(Path(sys.executable).with_name("pythonw.exe")), str(launcher)],
                                timeout=30, check=False)
        return result.returncode, (root / "last-sync.log").read_text(encoding="utf-8")

    def test_python_and_child_share_hidden_console(self):
        source = ("import os, subprocess, sys\n"
                  "assert sys.argv[1:] == ['sync']\n"
                  "assert os.environ['GIT_TERMINAL_PROMPT'] == '0'\n"
                  "assert os.environ['GCM_INTERACTIVE'] == 'Never'\n"
                  f"exec({PROBE!r})\n"
                  f"print(subprocess.check_output([sys.executable, '-c', {PROBE!r}], text=True))\n"
                  "print('sync succeeded')\n")
        code, log = self.run_launcher(source)
        self.assertEqual(code, 0, log)
        probes = [json.loads(line) for line in log.splitlines() if line.startswith('{')]
        self.assertEqual(probes, [{"console": True, "visible": False}] * 2)
        self.assertIn("sync succeeded", log)
        self.assertIn("Exit code: 0", log)

    def test_failure_is_logged_and_propagated(self):
        code, log = self.run_launcher("import sys\nprint('test failure', file=sys.stderr)\nsys.exit(7)\n")
        self.assertEqual(code, 7)
        self.assertIn("test failure", log)
        self.assertIn("Exit code: 7", log)

    def test_missing_state_is_logged(self):
        code, log = self.run_launcher("raise AssertionError('must not run')", state=False)
        self.assertEqual(code, 1)
        self.assertIn("FileNotFoundError", log)


if __name__ == "__main__":
    unittest.main()
