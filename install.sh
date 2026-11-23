#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/auto-logbook"
nvim_plugin_dir="${XDG_DATA_HOME:-$HOME/.local/share}/nvim/site/plugin"
claude_skills_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"

journal=""
template=""
section=""
ticket_keys=""
uninstall=0

usage() {
    cat <<EOF
Usage: $(basename "$0") --journal DIR [options]
       $(basename "$0") --uninstall

Installs:
  note, idea, decision,   with 'uv tool install --editable'
  logbook
  git hooks               git config --global core.hooksPath $repo/hooks
  Neovim plugin           link in $nvim_plugin_dir
  Claude Code skill       link in $claude_skills_dir
  configuration           $config_dir/config.toml, only when it does not exist

Options:
  --journal DIR       Directory of the day files. Required for a first install.
  --template FILE     Template a new day file is created from.
  --section NAME      Level-two heading entries go under. Default: Log.
  --ticket-keys KEYS  Comma-separated Jira project keys, such as AM,SE. Default: any.
  --uninstall         Remove everything except the configuration and the journal.
  -h, --help          Show this help.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --journal) journal="$2"; shift 2 ;;
        --template) template="$2"; shift 2 ;;
        --section) section="$2"; shift 2 ;;
        --ticket-keys) ticket_keys="$2"; shift 2 ;;
        --uninstall) uninstall=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

remove_link() {
    if [ -L "$1" ] && [[ "$(readlink "$1")" == "$repo"/* ]]; then
        rm "$1"
        echo "Removed $1"
    fi
}

toml_string() {
    local value=${1//\\/\\\\}
    printf '"%s"' "${value//\"/\\\"}"
}

if [ "$uninstall" -eq 1 ]; then
    uv tool uninstall auto-logbook || true
    if [ "$(git config --global --get core.hooksPath || true)" = "$repo/hooks" ]; then
        git config --global --unset core.hooksPath
        echo "Unset global core.hooksPath"
    fi
    remove_link "$nvim_plugin_dir/auto_logbook.lua"
    remove_link "$claude_skills_dir/logbook-summary"
    echo "Kept $config_dir and the journal."
    exit 0
fi

command -v uv >/dev/null || { echo "uv is not on PATH. Install uv first." >&2; exit 1; }
command -v git >/dev/null || { echo "git is not on PATH." >&2; exit 1; }

current_hooks=$(git config --global --get core.hooksPath || true)
if [ -n "$current_hooks" ] && [ "$current_hooks" != "$repo/hooks" ]; then
    echo "Global core.hooksPath is already $current_hooks. Unset it or merge the hooks by hand." >&2
    exit 1
fi

if [ ! -f "$config_dir/config.toml" ]; then
    if [ -z "$journal" ]; then
        echo "--journal is required for a first install." >&2
        exit 2
    fi
    journal=$(realpath -m "${journal/#\~/$HOME}")
    mkdir -p "$config_dir" "$journal"
    {
        echo "journal = $(toml_string "$journal")"
        if [ -n "$template" ]; then
            template=$(realpath -m "${template/#\~/$HOME}")
            echo "template = $(toml_string "$template")"
        fi
        [ -n "$section" ] && echo "section = $(toml_string "$section")"
        if [ -n "$ticket_keys" ]; then
            keys=""
            IFS=, read -ra parts <<<"$ticket_keys"
            for key in "${parts[@]}"; do keys+="${keys:+, }$(toml_string "$key")"; done
            echo "ticket_keys = [$keys]"
        fi
    } >"$config_dir/config.toml"
    echo "Wrote $config_dir/config.toml"
elif [ -n "$journal$template$section$ticket_keys" ]; then
    echo "Kept the existing $config_dir/config.toml. Edit it to change the options." >&2
fi

uv tool install --force --editable "$repo"

git config --global core.hooksPath "$repo/hooks"
echo "Set global core.hooksPath to $repo/hooks"

mkdir -p "$nvim_plugin_dir" "$claude_skills_dir"
ln -sfn "$repo/nvim/auto_logbook.lua" "$nvim_plugin_dir/auto_logbook.lua"
echo "Linked $nvim_plugin_dir/auto_logbook.lua"
ln -sfn "$repo/claude/skills/logbook-summary" "$claude_skills_dir/logbook-summary"
echo "Linked $claude_skills_dir/logbook-summary"

if ! command -v logbook >/dev/null; then
    echo "$(uv tool dir --bin) is not on PATH. Add it to use note and logbook." >&2
fi
