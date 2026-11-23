"""Curses browser for entries, tickets and projects, with ticket assignment."""

import curses
from dataclasses import dataclass, field
from enum import Enum

from . import views
from .config import edit_registry
from .topics import TicketKey, TopicPath

ENTER_KEYS = (10, 13, curses.KEY_ENTER)
ESCAPE = 27
TAB = 9
CTRL_D = 4
CTRL_U = 21
NEW_PROJECT = "+ new project"


class View(Enum):
    """The three lists the browser switches between, in tab order."""

    ENTRIES = "entries"
    TICKETS = "tickets"
    PROJECTS = "projects"


ORDER = list(View)
HELP = {
    View.ENTRIES: "tab view  / filter  u unassigned  a assign  d unassign  c clear  q quit",
    View.TICKETS: "tab view  / filter  u unassigned  a assign  d unassign  enter entries  q quit",
    View.PROJECTS: "tab view  / filter  n new  x remove  enter entries  c clear  r reload  q quit",
}


@dataclass
class Item:
    """One selectable line.

    Attributes:
        text: Line shown.
        key: Ticket or project the line stands for. None for an entry.
        unassigned: Highlight the line as having no project.
        tickets: Tickets the line can be assigned through.
    """

    text: str
    key: TopicPath | TicketKey | None = None
    unassigned: bool = False
    tickets: list[TicketKey] = field(default_factory=list)


@dataclass
class Filters:
    """Filters on one view.

    Attributes:
        text: Case-insensitive text a line must contain.
        unassigned: Show only lines with no project.
        selector: Topic or ticket the entries view is narrowed to.
    """

    text: str = ""
    unassigned: bool = False
    selector: TopicPath | TicketKey | None = None

    def describe(self):
        """Return the active filters as a short label."""
        parts = []

        if self.selector:
            parts.append(f"in {self.selector}")

        if self.text:
            parts.append(f"/{self.text}")

        if self.unassigned:
            parts.append("unassigned")

        return " ".join(parts)


def _entry_items(rows, filters):
    kept = views.filter_rows(
        rows, selector=filters.selector, unassigned=filters.unassigned, text=filters.text
    )
    items = []

    for row in reversed(kept):
        entry = row.entry
        box = f"{entry.box} " if entry.checkbox else ""
        when = f"{entry.timestamp:%Y-%m-%d %H:%M}"
        line = f"{when}  {box}{entry.kind:<8}  {row.path_text}  {entry.message}"

        items.append(Item(text=line, unassigned=not row.project, tickets=row.tickets))

    return items


def _summary_items(summaries, filters):
    text = filters.text.lower()
    items = []

    for summary in summaries:
        if filters.unassigned and summary.project:
            continue

        last = f"{summary.last:%Y-%m-%d}" if summary.last else "-"
        counts = f"{summary.entries:>5} entries {summary.open_tasks:>3} open"
        line = f"{summary.label:<24} {summary.project_text:<24} {counts}  {last}"

        if text and text not in line.lower():
            continue

        tickets = [summary.name] if isinstance(summary.name, TicketKey) else []
        item = Item(text=line, key=summary.name, unassigned=not summary.project, tickets=tickets)

        items.append(item)

    return items


def visible_items(view, logbook, filters):
    """Return the lines of `view` that pass `filters`.

    Args:
        view: The view to list.
        logbook: The resolved journal.
        filters: Filters to apply.
    """
    if view is View.ENTRIES:
        return _entry_items(logbook.rows, filters)

    if view is View.TICKETS:
        return _summary_items(views.ticket_summaries(logbook), filters)

    return _summary_items(views.project_summaries(logbook), filters)


class Browser:
    """Curses state and drawing for `logbook tui`."""

    def __init__(self, screen, config):
        """Load the journal and set up colours.

        Args:
            screen: Curses window from `curses.wrapper`.
            config: Logbook configuration.
        """
        self.screen = screen
        self.config = config
        self.view = View.ENTRIES
        self.filters = {view: Filters() for view in View}
        self.selected = 0
        self.top = 0
        self.status = ""

        curses.curs_set(0)

        if curses.has_colors():
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_MAGENTA, -1)
            curses.init_pair(2, curses.COLOR_CYAN, -1)

        self.reload()

    def reload(self):
        self.logbook = views.load_logbook(self.config)

        self.refresh_items()

    def refresh_items(self):
        """Re-filter the current view without re-reading the journal."""
        self.items = visible_items(self.view, self.logbook, self.filters[self.view])
        self.selected = min(self.selected, max(len(self.items) - 1, 0))

    def current(self):
        if not self.items:
            return None

        return self.items[self.selected]

    def _draw_tabs(self, width):
        column = 0

        for view in View:
            label = f" {view.value} "
            attribute = curses.A_REVERSE if view is self.view else curses.A_BOLD

            self.screen.addnstr(0, column, label, max(width - column - 1, 0), attribute)
            column += len(label) + 1

        described = self.filters[self.view].describe()

        if described and column < width - 1:
            self.screen.addnstr(0, column + 1, described, width - column - 2, curses.color_pair(2))

    def _scroll_to_selection(self, visible):
        if self.selected < self.top:
            self.top = self.selected
        elif self.selected >= self.top + visible:
            self.top = self.selected - visible + 1

    def draw(self):
        height, width = self.screen.getmaxyx()
        visible = height - 3

        self.screen.erase()
        self._draw_tabs(width)
        self._scroll_to_selection(visible)

        for offset, item in enumerate(self.items[self.top : self.top + visible]):
            attribute = curses.color_pair(1) if item.unassigned else curses.A_NORMAL

            if self.top + offset == self.selected:
                attribute |= curses.A_REVERSE

            self.screen.addnstr(offset + 1, 0, item.text.ljust(width - 1), width - 1, attribute)

        if not self.items:
            self.screen.addnstr(1, 0, "Nothing to show", width - 1, curses.A_DIM)

        self.screen.addnstr(height - 2, 0, self.status, width - 1, curses.A_BOLD)
        self.screen.addnstr(height - 1, 0, HELP[self.view], width - 1, curses.A_DIM)
        self.screen.refresh()

    def prompt(self, label, initial=""):
        """Read a line of text on the status line. Return None on Escape."""
        height, width = self.screen.getmaxyx()
        text = initial

        curses.curs_set(1)

        try:
            while True:
                self.screen.move(height - 2, 0)
                self.screen.clrtoeol()
                self.screen.addnstr(height - 2, 0, f"{label}{text}", width - 1)

                key = self.screen.get_wch()

                if key in ("\n", "\r", curses.KEY_ENTER):
                    return text

                if key == "\x1b":
                    return None

                if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    text = text[:-1]
                elif isinstance(key, str) and key.isprintable():
                    text += key
        finally:
            curses.curs_set(0)

    def pick(self, title, options):
        """Show `options` in a box and return the index of the chosen one, or None on Escape."""
        height, width = self.screen.getmaxyx()
        box_height = min(len(options) + 2, height - 2)
        box_width = min(max([len(option) for option in options] + [len(title)]) + 4, width - 2)
        visible = box_height - 2
        window = curses.newwin(box_height, box_width, 1, 2)
        selected = 0
        top = 0

        window.keypad(True)

        while True:
            if selected < top:
                top = selected
            elif selected >= top + visible:
                top = selected - visible + 1

            window.erase()
            window.box()
            window.addnstr(0, 1, f" {title} ", box_width - 2, curses.A_BOLD)

            for offset, option in enumerate(options[top : top + visible]):
                attribute = curses.A_REVERSE if top + offset == selected else curses.A_NORMAL

                window.addnstr(offset + 1, 1, option.ljust(box_width - 2), box_width - 2, attribute)

            window.refresh()

            key = window.getch()

            if key in (ord("j"), curses.KEY_DOWN):
                selected = min(selected + 1, len(options) - 1)
            elif key in (ord("k"), curses.KEY_UP):
                selected = max(selected - 1, 0)
            elif key in ENTER_KEYS:
                return selected
            elif key in (ESCAPE, ord("q")):
                return None

    def _prompt_project(self):
        """Read a project name on the status line. Return None when none is given."""
        text = self.prompt("New project: ")

        if text is None:
            return None

        return TopicPath.parse(text)

    def _pick_project(self, title):
        """Pick a registered project, or name a new one. Return None on Escape."""
        projects = sorted(self.logbook.registry.projects)
        chosen = self.pick(title, [NEW_PROJECT, *(str(project) for project in projects)])

        if chosen is None:
            return None

        if chosen == 0:
            return self._prompt_project()

        return projects[chosen - 1]

    def switch(self, view):
        """Show `view` from the top."""
        self.view = view
        self.selected = 0
        self.top = 0

        self.refresh_items()

    def chosen_ticket(self):
        """Return the ticket the selected line acts on, asking when it has several."""
        item = self.current()

        if not item or not item.tickets:
            self.status = "No ticket on this line"

            return None

        if len(item.tickets) == 1:
            return item.tickets[0]

        chosen = self.pick("Ticket", [str(ticket) for ticket in item.tickets])

        if chosen is None:
            return None

        return item.tickets[chosen]

    def assign(self):
        """Assign the selected ticket to a project picked from a list."""
        if self.view is View.PROJECTS:
            return

        ticket = self.chosen_ticket()

        if not ticket:
            return

        project = self._pick_project(f"Assign {ticket}")

        if project is None:
            return

        with edit_registry(self.config.state) as registry:
            registry.assign(ticket, project)

        self.status = f"{ticket} -> {project}"

        self.reload()

    def unassign(self):
        """Remove the project of the selected ticket."""
        if self.view is View.PROJECTS:
            return

        ticket = self.chosen_ticket()

        if not ticket:
            return

        with edit_registry(self.config.state) as registry:
            registry.unassign(ticket)

        self.status = f"{ticket} unassigned"

        self.reload()

    def new_project(self):
        """Register a project named on the status line."""
        project = self._prompt_project()

        if project is None:
            return

        with edit_registry(self.config.state) as registry:
            registry.register(project)

        self.status = f"Project {project} registered"

        self.reload()

    def _selected_project(self):
        item = self.current()

        if self.view is not View.PROJECTS:
            return None

        if not item or item.key not in self.logbook.registry.projects:
            return None

        return item.key

    def remove_project(self):
        """Unregister the selected project after confirmation."""
        name = self._selected_project()

        if name is None:
            self.status = "Select a registered project"

            return

        if self.prompt(f"Remove {name}? [y/N] ") not in ("y", "Y"):
            return

        with edit_registry(self.config.state) as registry:
            registry.remove(name)

        self.status = f"Project {name} removed"

        self.reload()

    def open_entries(self):
        """Show the entries under the selected project or ticket."""
        item = self.current()

        if self.view is View.ENTRIES or not item:
            return

        self.filters[View.ENTRIES] = Filters(selector=item.key)

        self.switch(View.ENTRIES)

    def _move(self, key):
        """Move the selection for a navigation key. Return False for any other key."""
        last = max(len(self.items) - 1, 0)
        page = self.screen.getmaxyx()[0] // 2

        if key in (ord("j"), curses.KEY_DOWN):
            self.selected = min(self.selected + 1, last)
        elif key in (ord("k"), curses.KEY_UP):
            self.selected = max(self.selected - 1, 0)
        elif key in (ord("g"), curses.KEY_HOME):
            self.selected = 0
        elif key in (ord("G"), curses.KEY_END):
            self.selected = last
        elif key in (curses.KEY_NPAGE, CTRL_D):
            self.selected = min(self.selected + page, last)
        elif key in (curses.KEY_PPAGE, CTRL_U):
            self.selected = max(self.selected - page, 0)
        else:
            return False

        return True

    def _filter(self, key):
        """Change the filters for a filter key. Return False for any other key."""
        filters = self.filters[self.view]

        if key == ord("/"):
            text = self.prompt("/", filters.text)

            if text is not None:
                filters.text = text
        elif key == ord("u"):
            filters.unassigned = not filters.unassigned
        elif key == ord("c"):
            self.filters[self.view] = Filters()
        else:
            return False

        self.refresh_items()

        return True

    def handle(self, key):
        """Act on one key press. Return False to quit."""
        self.status = ""

        if key in (ord("q"), ESCAPE):
            return False

        if self._move(key) or self._filter(key):
            return True

        if key == TAB:
            self.switch(ORDER[(ORDER.index(self.view) + 1) % len(ORDER)])
        elif key == curses.KEY_BTAB:
            self.switch(ORDER[(ORDER.index(self.view) - 1) % len(ORDER)])
        elif key in (ord("1"), ord("2"), ord("3")):
            self.switch(ORDER[key - ord("1")])
        elif key == ord("a"):
            self.assign()
        elif key == ord("d"):
            self.unassign()
        elif key == ord("n"):
            self.new_project()
        elif key == ord("x"):
            self.remove_project()
        elif key in ENTER_KEYS:
            self.open_entries()
        elif key == ord("r"):
            self.reload()

            self.status = "Reloaded"

        return True


def _loop(screen, config):
    browser = Browser(screen, config)

    screen.keypad(True)

    while True:
        browser.draw()

        if not browser.handle(screen.getch()):
            return


def run(config):
    """Run the browser until the user quits."""
    curses.set_escdelay(25)
    curses.wrapper(_loop, config)
