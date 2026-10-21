"""Run the installed Windows sync with a hidden console shared by its children."""

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


def main():
    state_root = Path(__file__).resolve().parent
    # Keep only the latest run, including errors that pythonw cannot display.
    with (state_root / "last-sync.log").open("w", encoding="utf-8") as output:
        print(datetime.now().astimezone().isoformat(), file=output, flush=True)
        try:
            state = json.loads((state_root / "state.json").read_text(encoding="utf-8"))
            python = Path(sys.executable).with_name("python.exe")
            # A hidden console is inherited by Git and other console children.
            # pythonw alone would let those children create visible consoles.
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never",
                               PYTHONIOENCODING="utf-8")
            result = subprocess.run(
                [str(python), str(Path(state["repo"]) / "agent_home.py"), "sync"],
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                startupinfo=startup, env=environment,
            )
            print(f"Exit code: {result.returncode}", file=output)
            return result.returncode
        except Exception:
            traceback.print_exc(file=output)
            return 1


if __name__ == "__main__":
    sys.exit(main())
