"""Turn git and Neovim events into entries."""

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_registry
from .entry import Entry
from .topics import TicketKey, hashtag_topic, split_topic

#: A branch whose newest reflog record is a creation this recent is new, not revisited.
NEW_BRANCH_AGE = timedelta(seconds=30)
NVIM_FILES_SHOWN = 5
REFLOG_TIME_PATTERN = re.compile(r"@\{(\d+)\}$")
BRANCH_CREATED = "branch: Created from"


def _git(repo, *arguments):
    command = ["git", "-C", str(repo), *arguments]
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    return result.stdout.strip() if result.returncode == 0 else ""


def _now():
    return datetime.now().replace(microsecond=0)


def _topic(pattern, *texts):
    """Return the first `#project/topic` tag, else the first ticket key, in `texts`."""
    for text in texts:
        tag = hashtag_topic(text or "")

        if tag:
            return tag

    for text in texts:
        match = pattern.search(text or "")

        if match:
            return TicketKey.parse(match.group(0)).as_topic()

    return None


def _rebasing(repo):
    for name in ("rebase-merge", "rebase-apply"):
        state = _git(repo, "rev-parse", "--path-format=absolute", "--git-path", name)

        if Path(state).exists():
            return True

    return False


def commit_entry(config, repo):
    """Return the entry for the commit at `HEAD` of `repo`, or None during a rebase."""
    top = _git(repo, "rev-parse", "--show-toplevel")

    if not top or _rebasing(repo):
        return None

    sha, _, subject = _git(repo, "log", "-1", "--format=%h%x1f%s").partition("\x1f")
    branch = _git(repo, "symbolic-ref", "--short", "-q", "HEAD") or "detached"

    return Entry(
        timestamp=_now(),
        kind="commit",
        message=f"{subject} ({Path(top).name}@{branch} {sha})",
        topic=_topic(config.tickets, subject, branch),
    )


def branch_entry(config, repo, branch_checkout):
    """Return the entry for a branch created by the checkout that just ran, or None.

    Args:
        config: Logbook configuration.
        repo: Repository the checkout ran in.
        branch_checkout: The checkout switched branches rather than files.
    """
    if not branch_checkout:
        return None

    branch = _git(repo, "symbolic-ref", "--short", "-q", "HEAD")

    if not branch:
        return None

    newest = ["-n", "1", f"refs/heads/{branch}"]
    record = _git(repo, "reflog", "show", "--date=unix", "--format=%gd%x1f%gs", *newest)
    selector, _, subject = record.partition("\x1f")
    created = REFLOG_TIME_PATTERN.search(selector)

    if not subject.startswith(BRANCH_CREATED) or not created:
        return None

    if datetime.now() - datetime.fromtimestamp(int(created.group(1))) > NEW_BRANCH_AGE:
        return None

    start = subject.removeprefix(BRANCH_CREATED).strip()
    top = _git(repo, "rev-parse", "--show-toplevel")

    return Entry(
        timestamp=_now(),
        kind="branch",
        message=f"Created {branch} in {Path(top).name} from {start}",
        topic=_topic(config.tickets, branch),
    )


def _duration(elapsed):
    minutes = int(elapsed.total_seconds() // 60)

    if minutes < 60:
        return f"{minutes}m"

    return f"{minutes // 60}h {minutes % 60:02d}m"


def _repository_of(path, cwd):
    """Return the repository holding `path`, or `cwd` when it is in none."""
    top = ""

    if path.parent.exists():
        top = _git(path.parent, "rev-parse", "--show-toplevel")

    if top:
        return Path(top)

    return cwd.resolve()


def _display_name(path, root):
    if path.is_relative_to(root):
        return str(path.relative_to(root))

    return str(path)


def _with_summary(summary, details):
    if summary:
        return f"{summary} ({details})"

    return details


def _nvim_entry(config, root, paths, elapsed, summary, summary_topic):
    names = sorted({_display_name(path, root) for path in paths})
    shown = ", ".join(names[:NVIM_FILES_SHOWN])

    if len(names) > NVIM_FILES_SHOWN:
        shown += f" and {len(names) - NVIM_FILES_SHOWN} more"

    branch = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    where = f"{root.name}@{branch}" if branch else root.name
    plural = "file" if len(names) == 1 else "files"
    details = f"Edited {len(names)} {plural} in {where} over {_duration(elapsed)}: {shown}"

    return Entry(
        timestamp=_now(),
        kind="nvim",
        message=_with_summary(summary, details),
        topic=summary_topic or _topic(config.tickets, branch),
    )


def _summary_entry(config, cwd, summary, summary_topic):
    """Return the entry for a summary given with no files written."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    root = Path(top) if top else cwd.resolve()
    branch = _git(root, "symbolic-ref", "--short", "-q", "HEAD")

    return Entry(
        timestamp=_now(),
        kind="nvim",
        message=f"{summary} (in {root.name})",
        topic=summary_topic or _topic(config.tickets, branch),
    )


def nvim_entries(config, cwd, files, started, summary=None):
    """Return one entry per repository for the files a Neovim session wrote.

    Files inside the journal directory are skipped, so editing the journal does not
    log itself. A summary with no files left to log gives one entry for `cwd`.

    Args:
        config: Logbook configuration.
        cwd: Working directory of the session. Files outside any repository are
            grouped under it.
        files: Paths the session wrote.
        started: When the session, or the span since the last entry, started.
        summary: Text the user gave for the session. It leads each entry's message.
            A leading topic, as `note` takes one, is the entries' topic in place of
            the branch's ticket.
    """
    journal = config.journal.resolve()
    groups = {}

    for name in files:
        path = Path(name).resolve()

        if path.is_relative_to(journal):
            continue

        groups.setdefault(_repository_of(path, Path(cwd)), []).append(path)

    summary_topic = None

    if summary:
        registry = load_registry(config.state)
        summary_topic, summary = split_topic(summary.split(), registry, config.tickets)

    if not groups and summary:
        return [_summary_entry(config, Path(cwd), summary, summary_topic)]

    elapsed = datetime.now() - started

    return [
        _nvim_entry(config, root, paths, elapsed, summary, summary_topic)
        for root, paths in groups.items()
    ]
