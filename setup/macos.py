"""Install or remove the current user's macOS LaunchAgent."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys

LABEL = "io.github.agent-home.sync"
REPO = Path(__file__).resolve().parents[1]


def launchctl(*args, check=True):
    return subprocess.run(["/bin/launchctl", *args], check=check,
                          capture_output=True, text=True)


def schedule(home, remove=False):
    plist = home / "Library/LaunchAgents" / f"{LABEL}.plist"
    state = home / ".agent-home"
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    if not remove:
        if not (state / "state.json").is_file():
            raise ValueError("Run install first.")
        # Fail before changing the plist when no graphical login session exists.
        launchctl("print", domain)

    # bootout errors must not be ignored for a registered job: uninstall must
    # leave the state intact if a scheduled sync could still be running.
    if launchctl("print", service, check=False).returncode == 0:
        launchctl("bootout", service)
    if remove:
        plist.unlink(missing_ok=True)
        return

    environment = {"PATH": os.environ.get("PATH", os.defpath),
                   "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never",
                   "PYTHONIOENCODING": "utf-8"}
    if os.environ.get("CODEX_HOME"):
        environment["CODEX_HOME"] = str(Path(os.environ["CODEX_HOME"]).expanduser().resolve())
    definition = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(REPO / "agent_home.py"), "sync"],
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "StartInterval": 15 * 60,
        "StandardOutPath": str(state / "sync.log"),
        "StandardErrorPath": str(state / "sync.log"),
    }
    plist.parent.mkdir(parents=True, exist_ok=True)
    # plistlib escapes paths containing spaces, ampersands and other XML syntax.
    temporary = plist.with_suffix(".plist.tmp")
    temporary.write_bytes(plistlib.dumps(definition))
    temporary.chmod(0o600)
    temporary.replace(plist)
    launchctl("enable", service)
    launchctl("bootstrap", domain, str(plist))


if __name__ == "__main__":
    try:
        schedule(Path.home().resolve(), remove=sys.argv[1:] == ["remove"])
    except subprocess.CalledProcessError as error:
        sys.exit(error.stderr.strip() or str(error))
    except (ValueError, OSError) as error:
        sys.exit(str(error))
