# agent-home

Global agent instructions and personal skills shared across computers and harnesses through Git.

## Set up your repository

You need Python 3.10+, Git, and GitHub authentication on each computer.

- **Public configuration:** fork this repository into your account.
- **Private configuration:** create an empty private repository, clone this public
  repository, and point `origin` at your private repository before adding personal
  content. GitHub forks of public repositories are always public.

For a private configuration, replace `YOUR-ACCOUNT` below with your GitHub username:

```sh
git clone https://github.com/adrilasar/agent-home.git
cd agent-home
git remote rename origin upstream
git remote add origin https://github.com/YOUR-ACCOUNT/agent-home-personal.git
git config remote.pushDefault origin
git push -u origin main
```

For a public fork, clone your fork and add the public project as `upstream`:

```sh
git remote add upstream https://github.com/adrilasar/agent-home.git
git config remote.pushDefault origin
```

`origin` is your repository; `upstream` is the public project. Make personal changes
in your own repository. The included `machines/example/` configuration is a starting
point: create a folder for each computer and add your instructions and skills.
Import existing instructions and skills before installing, then commit and push.

## Installation

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

Edit the repository sources, not the installed copies. Once changes reach your
repository's `main`, your computers receive them automatically. To sync immediately:

```sh
python3 agent_home.py sync
```

Sync fetches and applies `origin/main`, including skill removals. It stops if the
installation clone is not on `main`, has local changes, or has unpublished commits.
Develop changes in another clone or worktree to keep the installation clone clean.

### Receive project updates

In your development clone, fetch and merge improvements from the public project:

```sh
git switch main
git pull --ff-only origin main
git fetch upstream
git merge upstream/main
git push origin main
```

Resolve any merge conflicts before pushing. This keeps your personal content and
brings in project updates; it does not upload your content to the public project.
Automatic sync reads only `origin/main`, so you decide when to incorporate upstream
updates. For contributions to the public project, use a separate clone containing
only public content.

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
