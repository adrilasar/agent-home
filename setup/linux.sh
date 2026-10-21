#!/usr/bin/env bash
set -euo pipefail

units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
if [[ "${1:-}" == "remove" ]]; then
    if [[ -f "$units/agent-home-sync.timer" ]]; then
        systemctl --user disable --now agent-home-sync.timer
    fi
    if [[ -f "$units/agent-home-sync.service" ]]; then
        systemctl --user stop agent-home-sync.service
    fi
    rm -f "$units/agent-home-sync.service" "$units/agent-home-sync.timer"
    systemctl --user daemon-reload
    exit
fi

repo="$(cd -- "$(dirname -- "$0")/.." && pwd)"
python="$(command -v python3)"
[[ -f "$HOME/.agent-home/state.json" ]]
mkdir -p "$units"
cat > "$units/agent-home-sync.service" <<EOF
[Unit]
Description=Sync agent-home instructions and skills

[Service]
Type=oneshot
Environment=GIT_TERMINAL_PROMPT=0
ExecStart="$python" "$repo/agent_home.py" sync
EOF
cat > "$units/agent-home-sync.timer" <<'EOF'
[Unit]
Description=Sync agent-home every 15 minutes

[Timer]
OnStartupSec=2min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now agent-home-sync.timer
