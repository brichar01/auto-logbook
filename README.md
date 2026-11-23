# Auto logbook

Collects progress logs into a daily journal, tagged by time and grouped by
project, topic or ticket. Entries come from git commits and new branches, Neovim
sessions, Claude Code session summaries and the `note` command. `PLAN.md` holds
the design.

## Install

Needs `uv` and `git`. Neovim and Claude Code are optional.

```sh
./install.sh --journal ~/personal/Journal \
    --template ~/personal/Templates/__Daily_Note__.md \
    --ticket-keys AM,SE
```

The script:

- installs `note`, `idea`, `decision` and `logbook` with
  `uv tool install --editable`, so edits to this repository take effect at once,
- sets the global `core.hooksPath` to `hooks/`,
- links `nvim/auto_logbook.lua` into `~/.local/share/nvim/site/plugin/`,
- links the `logbook-summary` skill into `~/.claude/skills/`,
- writes `~/.config/auto-logbook/config.toml` when it does not exist.

`./install.sh --uninstall` removes all of it except the configuration and the
journal.

### Git hooks

A global `core.hooksPath` stops git running the hooks in a repository's
`.git/hooks`. Every hook in `hooks/` links to `hooks/dispatch`, which runs the
repository's own hook first and keeps its exit status.

`pre-commit install` refuses to run while `core.hooksPath` is set. Hide the
global configuration from it:

```sh
GIT_CONFIG_GLOBAL=/dev/null pre-commit install
```

Set `LOGBOOK_DISABLE=1` to stop the hooks recording.

## Configuration

`~/.config/auto-logbook/config.toml`, or the file in `$LOGBOOK_CONFIG`:

| Key | Default | Meaning |
|---|---|---|
| `journal` | none, required | Directory of `YYYY-MM-DD.md` day files. Subdirectories are read too. `$LOGBOOK_JOURNAL` overrides it. |
| `section` | `Log` | Level-two heading new entries go under. It is added to the day file when missing. |
| `template` | none | File a new day file starts from. Templater `tp.date.now()` and `tp.file.title`, and `{{date}}`, become the date. A new day file also gets `location` in its frontmatter, the wifi SSID from `nmcli` or `unknown`. |
| `ticket_keys` | any | Jira project keys that count as tickets. With none, `UTF-8` is a ticket too. |
| `state` | `~/.local/share/auto-logbook/state.json` | Registered projects and the ticket to project mapping. |

## The log

```text
- 2026-11-19 8:25:14 #aq1/theseus/firmware #idea Use a gasket
- [ ] 2026-11-19 8:25:14 #AM-123 #todo Send the report 📅 2026-11-25
- 2026-11-19 9:02:41 #AM-123 #commit AM-123 Add sizing (am100-analyser@AM-123-sizing 3f2a1c9)
```

The topic and the kind are Obsidian tags. A topic with spaces is written with
hyphens. Every line in a day file that has this form is read, wherever it is.
The due date uses the Obsidian Tasks format, so the Tasks plugin picks up the
todos.

| Source | Kind | Topic |
|---|---|---|
| `note` | `note`, `idea`, `decision`, `todo`, or `--kind` | as given |
| commit | `commit` | `#project/topic` in the subject, else a ticket in the subject or branch |
| new branch | `branch` | a ticket in the branch name |
| Neovim exit, `:Logbook` | `nvim` | a ticket in the branch |
| Claude Code | `claude` and others | chosen by the `logbook-summary` skill |

## Adding entries

```sh
note "Measured 3 mA idle"                        # no topic
note aq1/theseus/firmware --idea "Use a gasket"  # topic first
note "#aq1/theseus" Use a gasket                 # same, as a tag
note --decision AM-123 "Keep the 2025 SDK"
idea "#aq1/theseus" Use a gasket               # same as note --idea
decision AM-123 "Keep the 2025 SDK"            # same as note --decision
note --due fri AM-123 "Send the report"          # a todo
```

The first word is the topic when more words follow and it is a `#tag`, holds a
`/`, is a ticket key or is a registered project. `--due` takes `YYYY-MM-DD`,
`today`, `tomorrow`, `+3d`, `+1w` or a weekday.

`log` is a zsh builtin, so the command is `note`.

## Projects and tickets

An entry belongs to the longest registered project its topic starts with. An
entry with no such topic belongs to the project its first mapped ticket is
assigned to. The mapping is applied when the log is read, so assigning a ticket
later moves every past entry that mentions it.

```sh
logbook project add aq1/am100
logbook assign AM-123 aq1/am100     # registers the project if new
logbook unassign AM-123
logbook projects                    # * marks a topic no project claims
logbook tickets --unassigned
```

## Views

```sh
logbook show                           # everything, by day
logbook show aq1/am100 --since mon     # a project or topic prefix
logbook show AM-123                    # a ticket
logbook show -k todo --open            # open tasks
logbook show --unassigned -n 20
logbook show --json                    # also on projects and tickets
logbook show --no-colour
logbook tui
```

`logbook tui` has three views, entries, tickets and projects, switched with
`tab`. `/` filters, `u` shows only unassigned lines, `a` assigns the ticket on
the line to a project, `d` unassigns it, `n` adds a project, `x` removes one and
`enter` shows the entries of a ticket or project.

## Neovim

The plugin keeps the set of files saved since the last entry. Files in the
journal are left out.

- On exit, when files were saved, it asks `Enter session summary:`. The summary
  leads the entry and the list of files follows it. Escape adds no entry. An
  empty summary logs the files alone. With no UI, as in `nvim --headless`, it logs
  the files without asking.
- `:Logbook [summary]`, or `<Leader>nl`, adds an entry now and starts a new file
  set. With no argument it asks for the summary. A summary with no files saved
  is logged on its own.

Set `vim.g.auto_logbook_disable = true` to turn it off.

## Claude Code

Ask Claude Code to summarise the session. The `logbook-summary` skill writes a
summary line, then one line per topic, with `note`.

## Tests

```sh
uv run python -m unittest discover -s tests
```
