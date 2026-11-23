"""Read and append entries in the day files of the journal directory."""

import fcntl
import re
from pathlib import Path

from .entry import Entry

DAY_FILE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
HEADING_PATTERN = re.compile(r"^(#{1,6}) ")
TEMPLATE_DATE_PATTERN = re.compile(
    r"<%\s*tp\.(?:date\.now\(\s*\)|file\.title)\s*%>"
    r"|\{\{(?:date|title)\}\}"
)


def day_path(journal, day):
    """Return the day file for `day` in the top level of `journal`."""
    return Path(journal) / f"{day:%Y-%m-%d}.md"


def new_day_text(day, template):
    """Return the text of a new day file.

    Args:
        day: Date of the day file.
        template: File to start from, or None for an empty file. Templater
            `tp.date.now()` and `tp.file.title` tags and `{{date}}` and `{{title}}`
            become the date. Other template tags are left as they are.
    """
    if template is None:
        return ""

    return TEMPLATE_DATE_PATTERN.sub(day.isoformat(), Path(template).read_text())


def _is_fence(line):
    return line.lstrip().startswith(("```", "~~~"))


def _section_bounds(lines, title):
    """Return the index of the `title` heading and of the line that ends its section.

    The section ends at the next heading of level one or two, outside code fences.
    The heading index is None when there is no such heading.
    """
    start = None
    in_fence = False

    for index, current in enumerate(lines):
        if _is_fence(current):
            in_fence = not in_fence
            continue

        if in_fence:
            continue

        if start is None:
            if current.strip() == title:
                start = index

            continue

        heading = HEADING_PATTERN.match(current)

        if heading and len(heading.group(1)) <= 2:
            return start, index

    return start, len(lines)


def insert_into_section(text, section, line):
    """Return `text` with `line` added at the end of the `## section` heading.

    A missing section is added at the end of the text.
    """
    lines = text.splitlines()
    title = f"## {section}"
    start, end = _section_bounds(lines, title)

    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()

        if lines:
            lines.append("")

        lines.extend([title, line])

        return "\n".join(lines) + "\n"

    position = end

    while position - 1 > start and not lines[position - 1].strip():
        position -= 1

    lines.insert(position, line)

    return "\n".join(lines) + "\n"


def append_entry(config, entry):
    """Add `entry` to its day file, creating the file from the template if needed.

    Returns:
        The day file written to.
    """
    path = day_path(config.journal, entry.timestamp.date())

    path.parent.mkdir(parents=True, exist_ok=True)

    # Append mode creates the file without truncating it, so the lock is held before
    # the read. O_APPEND writes land at offset 0 after the truncate.
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        text = handle.read() or new_day_text(entry.timestamp.date(), config.template)

        handle.truncate(0)
        handle.write(insert_into_section(text, config.section, entry.format()))

    return path


def _is_hidden(path, journal):
    return any(part.startswith(".") for part in path.relative_to(journal).parts)


def day_files(journal):
    """Return every `YYYY-MM-DD.md` under `journal`, skipping hidden directories."""
    found = [
        path
        for path in Path(journal).rglob("*.md")
        if DAY_FILE_PATTERN.match(path.name) and not _is_hidden(path, journal)
    ]

    return sorted(found, key=lambda path: path.name)


def read_entries(journal):
    """Return every entry in the journal, oldest first."""
    entries = []

    for path in day_files(journal):
        lines = path.read_text(encoding="utf-8").splitlines()

        for number, line in enumerate(lines, start=1):
            entry = Entry.parse(line, source=path, number=number)

            if entry:
                entries.append(entry)

    entries.sort(key=lambda entry: entry.timestamp)

    return entries
