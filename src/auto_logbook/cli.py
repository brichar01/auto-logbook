"""Command line entry points: `note` adds an entry, `logbook` views and manages the log."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import capture, views
from .config import ConfigError, edit_registry, load_config, load_registry
from .entry import Entry, parse_day
from .journal import append_entry
from .topics import TicketKey, TopicPath, hashtag_topic, parse_selector


def _day(text):
    try:
        return parse_day(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a date: {text}") from error


def _topic(text):
    topic = TopicPath.parse(text)

    if topic is None:
        raise argparse.ArgumentTypeError(f"not a topic: {text!r}")

    return topic


def _ticket(text):
    try:
        return TicketKey.parse(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _epoch(text):
    return datetime.fromtimestamp(float(text))


def _now():
    return datetime.now().replace(microsecond=0)


def _is_topic_word(word, registry, pattern):
    """Return whether a leading note word names a topic rather than starting the message."""
    if any(character.isspace() for character in word):
        return False

    if word.startswith("#") or "/" in word:
        return True

    if pattern.fullmatch(word):
        return True

    return TopicPath.parse(word) in registry.projects


def split_topic(words, registry, pattern):
    """Split note words into a topic and a message.

    The first word is a topic when more words follow and it is a `#tag`, holds a
    `/`, is a ticket key or is a registered project. Otherwise the first
    `#project/topic` tag in the message is the topic, and stays in the message.

    Returns:
        A `(topic, message)` tuple. The topic is None when none is found.
    """
    if len(words) > 1 and _is_topic_word(words[0], registry, pattern):
        return TopicPath.parse(words[0]), " ".join(words[1:])

    message = " ".join(words)

    return hashtag_topic(message), message


def _add_kind_flags(parser):
    kind = parser.add_mutually_exclusive_group()

    for name in ("idea", "decision", "todo"):
        kind.add_argument(
            f"--{name}", dest="kind", action="store_const", const=name, help=f"Tag as #{name}"
        )

    kind.add_argument("--kind", dest="kind", help="Tag with any other kind, such as `claude`")
    parser.add_argument(
        "--due",
        type=_day,
        help="Due date of a #todo: YYYY-MM-DD, today, tomorrow, +3d, +1w or a weekday. "
        "Implies --todo",
    )


def note_parse_args(argv=None, kind=None):
    """Return the parsed command line of `note`, or of an alias that fixes the kind.

    Args:
        argv: Arguments to parse. Defaults to the process arguments.
        kind: Kind the alias fixes, such as `idea`, which is also the program name.
            None parses `note`, which takes the kind as a flag.
    """
    if kind is None:
        parser = argparse.ArgumentParser(
            prog="note",
            description="Add an entry to today's journal.",
            epilog="Examples: note aq1/theseus --idea 'Use a gasket'   "
            "note --due fri AM-123 'Send the report'",
        )

        _add_kind_flags(parser)
    else:
        parser = argparse.ArgumentParser(
            prog=kind,
            description=f"Add an entry tagged #{kind} to today's journal, as `note --{kind}` does.",
            epilog=f"Example: {kind} '#aq1/theseus' Use a gasket",
        )

        parser.set_defaults(kind=kind, due=None)

    parser.add_argument(
        "-t", "--topic", type=_topic, help="Topic, such as project/topic or a ticket key"
    )
    parser.add_argument("--config", type=Path, help="Configuration file")
    parser.add_argument(
        "words", nargs="+", metavar="[topic] message", help="Optional topic, then the message"
    )

    arguments = parser.parse_args(argv)

    if arguments.due and arguments.kind not in (None, "todo"):
        parser.error("--due only applies to a todo")

    return arguments


def note(config_path, words, kind, topic, due):
    """Write one entry to today's day file and print it.

    Args:
        config_path: Configuration file, or None for the default.
        words: Message words, optionally led by a topic.
        kind: Entry kind, or None for `note`, or `todo` when `due` is set.
        topic: Explicit topic. When None, it is taken from `words`.
        due: Due date of a todo, or None.
    """
    config = load_config(config_path)

    if topic is None:
        topic, message = split_topic(words, load_registry(config.state), config.tickets)
    else:
        message = " ".join(words)

    if kind is None and due:
        kind = "todo"
    elif kind is None:
        kind = "note"

    entry = Entry(
        timestamp=_now(), kind=kind, message=message, topic=topic, checkbox=kind == "todo", due=due
    )
    path = append_entry(config, entry)

    print(f"{entry.format()}  -> {path}")


def note_main(argv=None, kind=None):
    """Run `note`, or the alias that fixes `kind`."""
    arguments = note_parse_args(argv, kind)

    try:
        note(arguments.config, arguments.words, arguments.kind, arguments.topic, arguments.due)
    except ConfigError as error:
        sys.exit(str(error))


def idea_main(argv=None):
    note_main(argv, kind="idea")


def decision_main(argv=None):
    note_main(argv, kind="decision")


def _output_flags(parser):
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--no-colour", action="store_true", help="Do not colour the output")


def logbook_parse_args(argv=None):
    """Return the parsed `logbook` command line."""
    parser = argparse.ArgumentParser(prog="logbook", description="View and manage the logbook.")

    parser.add_argument("--config", type=Path, help="Configuration file")

    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="Print entries, grouped by day")

    show.add_argument(
        "selector", nargs="?", default="", help="Project or topic prefix, or a ticket key"
    )
    show.add_argument("-k", "--kind", action="append", default=[], help="Kind to show, repeatable")
    show.add_argument("--since", type=_day, help="First day")
    show.add_argument("--until", type=_day, help="Last day")
    show.add_argument("--open", action="store_true", help="Only unticked tasks")
    show.add_argument("--unassigned", action="store_true", help="Only entries with no project")
    show.add_argument("-n", "--limit", type=int, help="Only the newest N entries")
    _output_flags(show)

    projects = commands.add_parser("projects", help="List projects and unregistered topics")

    _output_flags(projects)

    project = commands.add_parser("project", help="Add or remove a project")
    project_commands = project.add_subparsers(dest="action", required=True)

    project_commands.add_parser("add", help="Register a project").add_argument("name", type=_topic)
    project_commands.add_parser("remove", help="Unregister a project").add_argument(
        "name", type=_topic
    )

    tickets = commands.add_parser("tickets", help="List tickets and their projects")

    tickets.add_argument("--unassigned", action="store_true", help="Only tickets with no project")
    _output_flags(tickets)

    assign = commands.add_parser("assign", help="Map a ticket to a project")

    assign.add_argument("ticket", type=_ticket)
    assign.add_argument("project", type=_topic)

    unassign = commands.add_parser("unassign", help="Remove a ticket's project")

    unassign.add_argument("ticket", type=_ticket)
    commands.add_parser("tui", help="Browse entries, tickets and projects")

    hook = commands.add_parser("capture", help="Record an event. Called by git hooks and Neovim")
    sources = hook.add_subparsers(dest="source", required=True)
    commit = sources.add_parser("commit", help="Record the commit at HEAD")

    commit.add_argument("--repo", type=Path, default=Path("."), help="Repository")

    checkout = sources.add_parser("checkout", help="Record a branch created by a checkout")

    checkout.add_argument("--repo", type=Path, default=Path("."), help="Repository")
    checkout.add_argument(
        "branch_checkout",
        type=lambda flag: flag == "1",
        help="Third post-checkout argument, 1 for a branch checkout",
    )

    nvim = sources.add_parser("nvim", help="Record files a Neovim session wrote")

    nvim.add_argument("--cwd", type=Path, required=True, help="Session working directory")
    nvim.add_argument("--started", type=_epoch, required=True, help="Session start, epoch seconds")
    nvim.add_argument("files", type=Path, nargs="*", help="Files written")

    return parser.parse_args(argv)


def show(config, selector, kinds, since, until, open_only, unassigned, limit, as_json, no_colour):
    """Print entries matching the filters. See `views.filter_rows` for the filters."""
    logbook = views.load_logbook(config)
    rows = views.filter_rows(logbook.rows, selector, kinds, since, until, open_only, unassigned)

    if limit:
        rows = rows[-limit:]

    views.print_rows(rows, views.use_colour(no_colour), as_json)


def list_projects(config, as_json, no_colour):
    """Print registered projects, then top-level topics no project claims."""
    summaries = views.project_summaries(views.load_logbook(config))

    views.print_summaries(summaries, views.use_colour(no_colour), as_json, "project")

    if as_json:
        return

    if any(not summary.registered for summary in summaries):
        print("* not registered. Add with `logbook project add NAME`.")


def list_tickets(config, unassigned, as_json, no_colour):
    """Print tickets with their project and counts."""
    summaries = views.ticket_summaries(views.load_logbook(config))

    if unassigned:
        summaries = [summary for summary in summaries if not summary.project]

    views.print_summaries(summaries, views.use_colour(no_colour), as_json, "ticket")


def add_project(config, project):
    """Register `project`."""
    with edit_registry(config.state) as registry:
        registry.register(project)

    print(f"Project {project} registered")


def remove_project(config, project):
    """Unregister `project` and unassign its tickets."""
    with edit_registry(config.state) as registry:
        removed = registry.remove(project)

    if not removed:
        sys.exit(f"No project {project}")

    print(f"Project {project} removed")


def assign_ticket(config, ticket, project):
    """Map `ticket` to `project`, registering the project if it is new."""
    if not config.tickets.fullmatch(str(ticket)):
        sys.exit(f"{ticket} is not one of the configured ticket keys")

    with edit_registry(config.state) as registry:
        registered = registry.assign(ticket, project)

    if registered:
        print(f"Project {project} registered")

    print(f"{ticket} -> {project}")


def unassign_ticket(config, ticket):
    """Remove the project of `ticket`."""
    with edit_registry(config.state) as registry:
        registry.unassign(ticket)

    print(f"{ticket} unassigned")


def _append_all(config, entries):
    for entry in entries:
        if entry:
            append_entry(config, entry)


def logbook_main(argv=None):
    arguments = logbook_parse_args(argv)

    try:
        config = load_config(arguments.config)
    except ConfigError as error:
        sys.exit(str(error))

    command = arguments.command

    if command == "show":
        show(
            config,
            selector=parse_selector(arguments.selector, config.tickets),
            kinds=arguments.kind,
            since=arguments.since,
            until=arguments.until,
            open_only=arguments.open,
            unassigned=arguments.unassigned,
            limit=arguments.limit,
            as_json=arguments.json,
            no_colour=arguments.no_colour,
        )
    elif command == "projects":
        list_projects(config, as_json=arguments.json, no_colour=arguments.no_colour)
    elif command == "project" and arguments.action == "add":
        add_project(config, arguments.name)
    elif command == "project":
        remove_project(config, arguments.name)
    elif command == "tickets":
        list_tickets(
            config,
            unassigned=arguments.unassigned,
            as_json=arguments.json,
            no_colour=arguments.no_colour,
        )
    elif command == "assign":
        assign_ticket(config, arguments.ticket, arguments.project)
    elif command == "unassign":
        unassign_ticket(config, arguments.ticket)
    elif command == "tui":
        from .tui import run

        run(config)
    elif arguments.source == "commit":
        _append_all(config, [capture.commit_entry(config, arguments.repo)])
    elif arguments.source == "checkout":
        entry = capture.branch_entry(config, arguments.repo, arguments.branch_checkout)

        _append_all(config, [entry])
    else:
        entries = capture.nvim_entries(config, arguments.cwd, arguments.files, arguments.started)

        _append_all(config, entries)
