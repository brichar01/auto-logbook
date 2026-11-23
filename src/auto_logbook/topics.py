"""Topic paths and ticket keys, the two things entries are grouped by."""

import re
from dataclasses import dataclass

TICKET_KEY_PATTERN = re.compile(r"([A-Z][A-Z0-9]+)-(\d+)")
HASHTAG_TOPIC_PATTERN = re.compile(r"(?<!\S)#([A-Za-z0-9_-]+/[A-Za-z0-9_/-]*)")


def ticket_pattern(keys):
    """Return the pattern that finds ticket keys such as `AM-123`.

    Args:
        keys: Jira project keys to accept. Empty accepts any upper-case key, which
            also matches strings such as `UTF-8`.
    """
    prefix = "|".join(re.escape(key) for key in keys) if keys else r"[A-Z][A-Z0-9]+"

    return re.compile(rf"\b(?:{prefix})-\d+\b")


@dataclass(frozen=True, order=True)
class TopicPath:
    """A `/`-separated topic such as `aq1/theseus/firmware`, written as an Obsidian tag.

    Attributes:
        segments: The parts between the slashes. None is empty or holds whitespace.
    """

    segments: tuple[str, ...]

    @classmethod
    def parse(cls, text):
        """Return the path `text` names, or None when it names none.

        A leading `#` and empty segments are dropped. Whitespace becomes `-`, since an
        Obsidian tag cannot hold a space.
        """
        cleaned = "-".join(text.split()).lstrip("#")
        segments = tuple(part for part in cleaned.split("/") if part)

        if not segments:
            return None

        return cls(segments)

    def __str__(self):
        return "/".join(self.segments)

    @property
    def head(self):
        """The first segment, as a path."""
        return TopicPath(self.segments[:1])

    def is_within(self, other):
        """Return whether this path is `other` or lies under it."""
        return self.segments[: len(other.segments)] == other.segments

    def prefixes(self):
        """Return this path and each of its ancestors, longest first."""
        return [TopicPath(self.segments[:length]) for length in range(len(self.segments), 0, -1)]

    def join(self, other):
        """Return `other` placed under this path."""
        return TopicPath(self.segments + other.segments)


@dataclass(frozen=True, order=True)
class TicketKey:
    """A Jira ticket key such as `AM-123`.

    Attributes:
        project: Jira project key, such as `AM`.
        number: Issue number within the project.
    """

    project: str
    number: int

    @classmethod
    def parse(cls, text):
        """Return the key in `text`, ignoring case.

        Raises:
            ValueError: `text` is not a ticket key.
        """
        match = TICKET_KEY_PATTERN.fullmatch(text.strip().upper())

        if not match:
            raise ValueError(f"{text} is not a ticket key")

        return cls(match.group(1), int(match.group(2)))

    @classmethod
    def find_all(cls, text, pattern):
        """Return the keys `pattern` finds in `text`, first mention first, without repeats."""
        return list(dict.fromkeys(cls.parse(found) for found in pattern.findall(text)))

    def __str__(self):
        return f"{self.project}-{self.number}"

    def as_topic(self):
        """Return the key as a one-segment topic, as an entry about the ticket carries."""
        return TopicPath((str(self),))


#: What a view can be narrowed to: everything under a topic, or everything mentioning a ticket.
Selector = TopicPath | TicketKey


def hashtag_topic(text):
    """Return the first `#project/topic` tag in `text`, or None."""
    match = HASHTAG_TOPIC_PATTERN.search(text)

    if not match:
        return None

    return TopicPath.parse(match.group(1))


def parse_selector(text, pattern):
    """Return the ticket key or topic path `text` names, or None when it is empty.

    Args:
        text: A ticket key in any case, or a topic path with or without `#`.
        pattern: Ticket key pattern from the configuration.
    """
    if pattern.fullmatch(text.strip().upper()):
        return TicketKey.parse(text)

    return TopicPath.parse(text)
