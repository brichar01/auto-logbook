"""Log entries and the one-line markdown format they are stored in.

An entry is one list item in a day file:

    - 2026-11-19 8:25:14 #project_name/topic #idea Note content
    - [ ] 2026-11-19 8:25:14 #project_name/topic #todo Note content 📅 2026-11-25
    - 2026-11-19 8:25:14 #note Note with no topic

The topic is an Obsidian tag. With two leading tags the first is the topic, so a
message with no topic that starts with a tag reads back as topic and kind.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .topics import TicketKey, TopicPath

#: Obsidian Tasks plugin field markers. A due date is written, a done date is only read.
DUE_MARKER = "📅"
DONE_MARKER = "✅"

ENTRY_PATTERN = re.compile(
    r"^\s*- (?:\[(?P<done>[ xX])\] )?"
    r"(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{1,2}:\d{2}:\d{2}) "
    r"(?:#(?P<topic>[^\s#]+) (?=#))?"
    r"#(?P<kind>[\w/-]+)(?: (?P<message>.*))?$"
)
TASK_FIELD_PATTERN = re.compile(rf"\s*({DUE_MARKER}|{DONE_MARKER}) (\d{{4}}-\d{{2}}-\d{{2}})")
RELATIVE_DAY_PATTERN = re.compile(r"\+(\d+)([dw])")
WEEKDAY_PATTERN = re.compile(r"[a-z]{3,}")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_day(text, today=None):
    """Parse a due date.

    Args:
        text: `YYYY-MM-DD`, `today`, `tomorrow`, `+Nd`, `+Nw` or a weekday name,
            which means the next such day after today.
        today: The date relative forms count from. Defaults to the current date.

    Raises:
        ValueError: `text` is none of the accepted forms.
    """
    today = today or date.today()
    lowered = text.strip().lower()

    if lowered == "today":
        return today

    if lowered == "tomorrow":
        return today + timedelta(days=1)

    relative = RELATIVE_DAY_PATTERN.fullmatch(lowered)

    if relative:
        unit = 7 if relative.group(2) == "w" else 1

        return today + timedelta(days=int(relative.group(1)) * unit)

    if WEEKDAY_PATTERN.fullmatch(lowered) and lowered[:3] in WEEKDAYS:
        ahead = (WEEKDAYS.index(lowered[:3]) - today.weekday() - 1) % 7 + 1

        return today + timedelta(days=ahead)

    return date.fromisoformat(lowered)


@dataclass
class Entry:
    """One line of the log.

    Attributes:
        timestamp: When the entry was made, to the second.
        kind: The tag after `#`, such as `idea`, `todo` or `commit`.
        message: Single-line text of the entry.
        topic: Hierarchical topic such as `project/topic`, or a ticket key as a topic.
        checkbox: The line carries a `[ ]` or `[x]` task box.
        done: The task box is ticked.
        due: Due date of a task.
        source: Day file the entry was read from.
        line: One-based line number in `source`.
    """

    timestamp: datetime
    kind: str
    message: str
    topic: TopicPath | None = None
    checkbox: bool = False
    done: bool = False
    due: date | None = None
    source: Path | None = None
    line: int | None = None

    def __post_init__(self):
        """Fold the message onto one line, since an entry is one list item."""
        self.message = " ".join(self.message.split())

    @property
    def is_open(self):
        """Whether the entry is an unticked task."""
        return self.checkbox and not self.done

    @property
    def box(self):
        """The task box as written, `[ ]` or `[x]`, or empty for an entry with none."""
        if not self.checkbox:
            return ""

        return "[x]" if self.done else "[ ]"

    def format(self):
        parts = ["-"]

        if self.checkbox:
            parts.append(self.box)

        parts.append(f"{self.timestamp:%Y-%m-%d} {self.timestamp.hour}:{self.timestamp:%M:%S}")

        if self.topic:
            parts.append(f"#{self.topic}")

        parts.append(f"#{self.kind}")

        if self.message:
            parts.append(self.message)

        if self.due:
            parts.append(f"{DUE_MARKER} {self.due.isoformat()}")

        return " ".join(parts)

    def tickets(self, pattern):
        """Return the ticket keys in the topic and message, first mention first."""
        return TicketKey.find_all(f"{self.topic or ''} {self.message}", pattern)

    @classmethod
    def parse(cls, line, source=None, number=None):
        """Return the entry on `line`, or None when the line is not an entry."""
        match = ENTRY_PATTERN.match(line.rstrip("\n"))

        if not match:
            return None

        message = match.group("message") or ""
        due = None

        for marker, value in TASK_FIELD_PATTERN.findall(message):
            if marker == DUE_MARKER:
                due = date.fromisoformat(value)

        box = match.group("done")
        stamp = f"{match.group('date')} {match.group('time')}"
        timestamp = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")

        return cls(
            timestamp=timestamp,
            kind=match.group("kind"),
            message=TASK_FIELD_PATTERN.sub("", message),
            topic=TopicPath.parse(match.group("topic") or ""),
            checkbox=box is not None,
            done=box in ("x", "X"),
            due=due,
            source=source,
            line=number,
        )
