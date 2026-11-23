"""Filter, summarise and print entries, projects and tickets."""

import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime

from .config import Registry, load_registry
from .entry import Entry
from .journal import read_entries
from .topics import TicketKey, TopicPath

PATH_WIDTH_LIMIT = 32
RESET = "\033[0m"
STYLES = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "path": "\033[36m",
    "due": "\033[33m",
    "overdue": "\033[31;1m",
    "unassigned": "\033[35m",
}
KIND_STYLES = {
    "todo": "\033[33m",
    "idea": "\033[32m",
    "decision": "\033[34;1m",
    "commit": "\033[36m",
    "branch": "\033[36m",
    "nvim": "\033[2m",
    "claude": "\033[35m",
}


def use_colour(no_colour, stream=None):
    """Return whether to colour output: not disabled, no `$NO_COLOR`, and a terminal."""
    stream = stream or sys.stdout

    return not no_colour and "NO_COLOR" not in os.environ and stream.isatty()


def _paint(text, style, colour):
    if colour and style:
        return f"{style}{text}{RESET}"

    return text


def _text(value):
    if value is None:
        return None

    return str(value)


@dataclass
class Row:
    """An entry with its resolved project and path.

    Attributes:
        entry: The entry.
        project: Registered project the entry belongs to, or None.
        path: `project/topic` path the entry is filtered and shown under, or None.
        tickets: Ticket keys the entry mentions.
    """

    entry: Entry
    project: TopicPath | None
    path: TopicPath | None
    tickets: list[TicketKey]

    @property
    def path_text(self):
        """The path as shown, `-` for none."""
        return _text(self.path) or "-"

    def to_json(self):
        entry = self.entry

        return {
            "timestamp": entry.timestamp.isoformat(),
            "kind": entry.kind,
            "topic": _text(entry.topic),
            "project": _text(self.project),
            "path": _text(self.path),
            "message": entry.message,
            "tickets": [str(ticket) for ticket in self.tickets],
            "checkbox": entry.checkbox,
            "done": entry.done,
            "due": _text(entry.due),
            "file": _text(entry.source),
            "line": entry.line,
        }


def resolve(entries, registry, pattern):
    """Return a `Row` for each entry."""
    return [
        Row(
            entry=entry,
            project=registry.project_of(entry, pattern),
            path=registry.path_of(entry, pattern),
            tickets=entry.tickets(pattern),
        )
        for entry in entries
    ]


@dataclass
class Logbook:
    """The journal resolved against the registry.

    Attributes:
        registry: Projects and the ticket mapping.
        rows: Every entry in the journal, oldest first.
    """

    registry: Registry
    rows: list[Row]


def load_logbook(config):
    """Read the registry and the journal, and resolve every entry."""
    registry = load_registry(config.state)
    rows = resolve(read_entries(config.journal), registry, config.tickets)

    return Logbook(registry=registry, rows=rows)


def matches(row, selector):
    """Return whether `row` mentions the ticket, or sits under the topic, `selector` names."""
    if selector is None:
        return True

    if isinstance(selector, TicketKey):
        return selector in row.tickets

    for path in (row.path, row.entry.topic):
        if path and path.is_within(selector):
            return True

    return False


def _in_range(day, since, until):
    if since and day < since:
        return False

    if until and day > until:
        return False

    return True


def _contains(row, text):
    return text.lower() in f"{row.path_text} {row.entry.kind} {row.entry.message}".lower()


def filter_rows(
    rows,
    selector=None,
    kinds=None,
    since=None,
    until=None,
    open_only=False,
    unassigned=False,
    text=None,
):
    """Return the rows that pass every given filter.

    Args:
        rows: Rows to filter.
        selector: Topic or ticket to narrow to.
        kinds: Entry kinds to keep. Empty keeps all.
        since: First day to keep.
        until: Last day to keep.
        open_only: Keep only unticked tasks.
        unassigned: Keep only rows with no project.
        text: Case-insensitive text the path or message must contain.
    """
    kept = []

    for row in rows:
        if kinds and row.entry.kind not in kinds:
            continue

        if not _in_range(row.entry.timestamp.date(), since, until):
            continue

        if open_only and not row.entry.is_open:
            continue

        if unassigned and row.project:
            continue

        if not matches(row, selector):
            continue

        if text and not _contains(row, text):
            continue

        kept.append(row)

    return kept


def _due_text(entry, colour, today):
    late = entry.due < today and entry.is_open
    style = STYLES["overdue"] if late else STYLES["due"]

    return _paint(f"due {entry.due.isoformat()}", style, colour)


def format_row(row, colour, path_width=0, today=None):
    """Return one printed line for `row`, without the date, padding the path to `path_width`."""
    today = today or date.today()
    entry = row.entry
    box = f"{entry.box} " if entry.checkbox else ""
    path_style = STYLES["path"] if row.project else STYLES["unassigned"]
    kind = _paint(f"{entry.kind:<8}", KIND_STYLES.get(entry.kind), colour)
    path = _paint(f"{row.path_text:<{path_width}}", path_style, colour)
    time = _paint(f"{entry.timestamp:%H:%M:%S}", STYLES["dim"], colour)
    line = f"  {time}  {kind}  {path}  {box}{entry.message}"

    if entry.due:
        line += "  " + _due_text(entry, colour, today)

    return line


def print_rows(rows, colour, as_json, stream=None):
    """Print rows grouped by day, or as a JSON list."""
    stream = stream or sys.stdout

    if as_json:
        json.dump([row.to_json() for row in rows], stream, indent=2)
        stream.write("\n")

        return

    path_width = min(max((len(row.path_text) for row in rows), default=0), PATH_WIDTH_LIMIT)
    day = None

    for row in rows:
        if row.entry.timestamp.date() != day:
            day = row.entry.timestamp.date()

            stream.write(_paint(f"{day:%Y-%m-%d %a}", STYLES["bold"], colour) + "\n")

        stream.write(format_row(row, colour, path_width) + "\n")


@dataclass
class Summary:
    """Counts for one project or ticket.

    Attributes:
        name: The project or ticket.
        project: Project a ticket maps to. For a project, the project itself.
        entries: Number of entries.
        open_tasks: Number of unticked tasks.
        last: Time of the newest entry, or None.
        registered: The project is registered, or the ticket is in the registry.
    """

    name: TopicPath | TicketKey
    project: TopicPath | None
    entries: int = 0
    open_tasks: int = 0
    last: datetime | None = None
    registered: bool = False

    @property
    def label(self):
        """The name, with `*` appended when it is not registered."""
        if self.registered:
            return str(self.name)

        return f"{self.name}*"

    @property
    def project_text(self):
        """The project as shown, `unassigned` for none."""
        return _text(self.project) or "unassigned"

    def count(self, row):
        self.entries += 1

        if row.entry.is_open:
            self.open_tasks += 1

        if self.last is None or row.entry.timestamp > self.last:
            self.last = row.entry.timestamp

    def to_json(self):
        return {
            "name": str(self.name),
            "project": _text(self.project),
            "entries": self.entries,
            "open_tasks": self.open_tasks,
            "last": self.last.isoformat() if self.last else None,
            "registered": self.registered,
        }


def ticket_summaries(logbook):
    """Return a summary per ticket seen in the journal or in the registry, newest first."""
    summaries = {
        key: Summary(name=key, project=project, registered=True)
        for key, project in logbook.registry.tickets.items()
    }

    for row in logbook.rows:
        for key in row.tickets:
            if key not in summaries:
                summaries[key] = Summary(name=key, project=None)

            summaries[key].count(row)

    def newest(summary):
        return summary.last or datetime.min

    return sorted(summaries.values(), key=newest, reverse=True)


def project_summaries(logbook):
    """Return a summary per registered project, then per unregistered top-level topic."""
    summaries = {
        name: Summary(name=name, project=name, registered=True)
        for name in logbook.registry.projects
    }

    for row in logbook.rows:
        if row.project:
            summaries[row.project].count(row)
            continue

        if not row.entry.topic or row.tickets:
            continue

        head = row.entry.topic.head

        if head not in summaries:
            summaries[head] = Summary(name=head, project=None)

        summaries[head].count(row)

    return sorted(summaries.values(), key=lambda summary: (not summary.registered, summary.label))


def print_summaries(summaries, colour, as_json, heading, stream=None):
    """Print project or ticket summaries as a table, or as a JSON list."""
    stream = stream or sys.stdout

    if as_json:
        json.dump([summary.to_json() for summary in summaries], stream, indent=2)
        stream.write("\n")

        return

    width = max([len(summary.label) for summary in summaries] + [len(heading)])
    header = f"{heading:<{width}}  {'project':<20}  entries  open  last"

    stream.write(_paint(header, STYLES["bold"], colour) + "\n")

    for summary in summaries:
        style = STYLES["path"] if summary.project else STYLES["unassigned"]
        project = _paint(f"{summary.project_text:<20}", style, colour)
        last = f"{summary.last:%Y-%m-%d}" if summary.last else "-"
        counts = f"{summary.entries:>7}  {summary.open_tasks:>4}"

        stream.write(f"{summary.label:<{width}}  {project}  {counts}  {last}\n")
