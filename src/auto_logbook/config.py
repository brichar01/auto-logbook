"""Configuration, and the project and ticket registry."""

import fcntl
import json
import os
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .topics import TicketKey, TopicPath, ticket_pattern


class ConfigError(Exception):
    """The configuration is missing or invalid."""


def default_config_path():
    """Return `$LOGBOOK_CONFIG`, or `config.toml` in the XDG config directory."""
    if os.environ.get("LOGBOOK_CONFIG"):
        return Path(os.environ["LOGBOOK_CONFIG"])

    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"

    return Path(base) / "auto-logbook" / "config.toml"


def default_state_path():
    """Return `state.json` in the XDG data directory."""
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"

    return Path(base) / "auto-logbook" / "state.json"


@dataclass
class Config:
    """Where the journal lives and how entries are written to it.

    Attributes:
        journal: Directory of `YYYY-MM-DD.md` day files. Subdirectories are read too.
        state: JSON file holding the project and ticket registry.
        section: Level-two heading in a day file that new entries go under.
        template: File a new day file is created from.
        ticket_keys: Jira project keys that count as tickets. Empty accepts any.
    """

    journal: Path
    state: Path
    section: str = "Log"
    template: Path | None = None
    ticket_keys: list[str] = field(default_factory=list)

    @property
    def tickets(self):
        return ticket_pattern(self.ticket_keys)


def load_config(path=None):
    """Read the configuration.

    `$LOGBOOK_JOURNAL` overrides the `journal` key.

    Args:
        path: Configuration file. Defaults to `default_config_path()`.

    Raises:
        ConfigError: No journal directory is configured.
    """
    path = Path(path) if path else default_config_path()
    values = {}

    if path.exists():
        with path.open("rb") as handle:
            values = tomllib.load(handle)

    journal = os.environ.get("LOGBOOK_JOURNAL") or values.get("journal")

    if not journal:
        raise ConfigError(f"No journal directory set. Set `journal` in {path} or $LOGBOOK_JOURNAL.")

    template = None

    if values.get("template"):
        template = Path(values["template"]).expanduser()

    return Config(
        journal=Path(journal).expanduser(),
        state=Path(values.get("state") or default_state_path()).expanduser(),
        section=values.get("section", "Log"),
        template=template,
        ticket_keys=list(values.get("ticket_keys", [])),
    )


@dataclass
class Registry:
    """Registered projects and the ticket to project mapping.

    Attributes:
        projects: Project to the time it was registered.
        tickets: Ticket to its project. None marks a known but unassigned ticket.
    """

    projects: dict[TopicPath, datetime] = field(default_factory=dict)
    tickets: dict[TicketKey, TopicPath | None] = field(default_factory=dict)

    def project_of(self, entry, pattern):
        """Return the project an entry belongs to, or None.

        The longest registered project that prefixes the topic wins. Otherwise the
        first ticket in the topic or message that maps to a project decides.
        """
        if entry.topic:
            for prefix in entry.topic.prefixes():
                if prefix in self.projects:
                    return prefix

        for ticket in entry.tickets(pattern):
            project = self.tickets.get(ticket)

            if project:
                return project

        return None

    def path_of(self, entry, pattern):
        """Return the full `project/topic` path an entry is shown and filtered under, or None."""
        project = self.project_of(entry, pattern)

        if project is None:
            return entry.topic

        if entry.topic and entry.topic.is_within(project):
            return entry.topic

        if entry.topic:
            return project.join(entry.topic)

        tickets = entry.tickets(pattern)

        if tickets:
            return project.join(tickets[0].as_topic())

        return project

    def register(self, project):
        """Register `project`. Return whether it was new."""
        if project in self.projects:
            return False

        self.projects[project] = datetime.now().replace(microsecond=0)

        return True

    def remove(self, project):
        """Unregister `project` and unassign its tickets. Return whether it was registered."""
        if self.projects.pop(project, None) is None:
            return False

        for ticket, assigned in self.tickets.items():
            if assigned == project:
                self.tickets[ticket] = None

        return True

    def assign(self, ticket, project):
        """Map `ticket` to `project`, registering the project. Return whether it was new."""
        registered = self.register(project)

        self.tickets[ticket] = project

        return registered

    def unassign(self, ticket):
        """Keep `ticket` known, with no project."""
        self.tickets[ticket] = None


@contextmanager
def _locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path.with_suffix(path.suffix + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load_registry(path):
    """Read the registry at `path`. A missing file is an empty registry."""
    if not path.exists():
        return Registry()

    data = json.loads(path.read_text())
    projects = {
        TopicPath.parse(name): datetime.fromisoformat(created)
        for name, created in data.get("projects", {}).items()
    }
    tickets = {
        TicketKey.parse(key): TopicPath.parse(project or "")
        for key, project in data.get("tickets", {}).items()
    }

    return Registry(projects=projects, tickets=tickets)


def _optional_text(project):
    if project is None:
        return None

    return str(project)


def _save_registry(registry, path):
    projects = {
        str(name): created.isoformat(timespec="seconds")
        for name, created in registry.projects.items()
    }
    tickets = {str(key): _optional_text(project) for key, project in registry.tickets.items()}
    text = json.dumps({"projects": projects, "tickets": tickets}, indent=2, sort_keys=True)
    temporary = path.with_suffix(".tmp")

    temporary.write_text(text + "\n")
    temporary.replace(path)


@contextmanager
def edit_registry(path):
    """Yield the registry at `path` under a lock, and save it on exit."""
    with _locked(path):
        registry = load_registry(path)

        yield registry
        _save_registry(registry, path)
