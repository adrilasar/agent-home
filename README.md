# agent-home

Sync global agent instructions and personal skills across computers and harnesses
through Git. Especially useful for remote-envs: remote development environments
where you launch and control agents from another computer.

## Set up your repository

You need Python 3.10+, Git, and GitHub authentication on each computer.

Your personal context stays in your private repository, while program updates
come from this public project.

Create an **empty private repository** on GitHub, then run:

```sh
git clone https://github.com/adrilasar/agent-home.git
cd agent-home
git remote rename origin upstream
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPO.git
git config remote.pushDefault origin
git push -u origin main
```

Replace `YOUR-ACCOUNT/YOUR-REPO` with your private repository's path.
`origin` points to your repository; `upstream` points to this public project
for future updates.

## Installation

Use `machines/example/` as a starting point: create a folder for each computer
and add your instructions and skills. Import existing instructions and skills
before installing, then commit and push.

Clone your repository into a permanent location on each computer and keep that
installation clone on `main`. Linux requires systemd user services; Windows uses
Task Scheduler. macOS scheduling is not supported.

From the clone, select the computer by its folder in `machines/` and the harnesses
to configure:

```sh
python3 agent_home.py install example codex claude
```

Replace `example` with your computer's folder name. You can select only `codex` or
only `claude`. When reinstalling, list all harnesses you want to keep. On Windows,
use `py -3` instead of `python3`.

Installation applies the files and schedules synchronization every 15 minutes.

## Usage and synchronization

Ask your agent to update your global instructions or personal skills, or edit the
repository sources yourself. The included `manage-personal-context` skill provides
agents with the repository and synchronization details.

Installed copies are generated. Once changes reach your repository's `main`, your
computers receive them automatically. To sync immediately:

```sh
python3 agent_home.py sync
```

Sync fetches and applies `origin/main`, including skill removals. It stops if the
installation clone is not on `main`, has local changes, or has unpublished commits.
Make edits in a separate clone or worktree to keep the installation clone clean.

### Receive project updates

To bring updates from the public project into your private repository:

```sh
git switch main
git pull --ff-only origin main
git fetch upstream
git merge upstream/main
git push origin main
```

You choose when to bring in public updates. To contribute improvements, fork the
public project.

## Organization

Sources are combined in this order:

1. `common/`: all computers and harnesses.
2. `harnesses/<harness>/`: one harness (`codex` or `claude`).
3. `machines/<computer>/`: one computer.
4. `machines/<computer>/harnesses/<harness>/`: one combination.

Each scope can contain:

- `FRAGMENT.md`: instructions concatenated into the global instructions file.
- `skills/<name>/SKILL.md` and resources: skills copied in full. Skill names must
  be unique across the selected scopes.

For the `example` computer, these fragments combine in order:

`common/FRAGMENT.md`:

```markdown
Delete this example 1.
```

`machines/example/FRAGMENT.md`:

```markdown
Delete this example 2.
```

The generated `AGENTS.md` or `CLAUDE.md` contains:

```markdown
Delete this example 1.

Delete this example 2.
```

Source comments are omitted here. Replace or remove both example fragments
before use.

Files are installed into:

- **Codex:** `~/.codex/AGENTS.md` and `~/.codex/skills/` (respects `CODEX_HOME`).
- **Claude Code:** `~/.claude/CLAUDE.md` and `~/.claude/skills/`.

This program manages global instructions and personal skills. It does not modify
instructions or skills inside project repositories.

## Uninstallation

```sh
python3 agent_home.py uninstall
```

Removes scheduled synchronization, state, and backups. Preserves installed
instructions, skills, and the repository clone.

## State and backups

- Installation state: `~/.agent-home/state.json`.
- Backups of preexisting files: `~/.agent-home/backups/`. Backups are removed during
  installation or synchronization once they are seven days old.

## License

MIT. See [LICENSE](LICENSE).
