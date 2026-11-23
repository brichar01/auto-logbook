"""Tests for entry formatting, journal writing, topic resolution and capture."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from pathlib import Path

from auto_logbook import cli, views
from auto_logbook.capture import branch_entry, commit_entry, nvim_entries
from auto_logbook.config import Config, Registry, edit_registry, load_config, load_registry
from auto_logbook.entry import Entry, parse_day
from auto_logbook.topics import TicketKey, TopicPath, parse_selector, ticket_pattern
from auto_logbook.journal import append_entry, insert_into_section, read_entries

ANY_TICKET = ticket_pattern([])
T = TopicPath.parse
K = TicketKey.parse
NOW = datetime(2026, 11, 19, 8, 0, 0)


class EntryTest(unittest.TestCase):
    def test_format_matches_plan(self):
        entry = Entry(datetime(2026, 11, 19, 8, 25, 14), "idea", "Note  content", T("project_name/topic"))
        self.assertEqual(entry.format(), "- 2026-11-19 8:25:14 #project_name/topic #idea Note content")

    def test_todo_round_trip(self):
        entry = Entry(
            datetime(2026, 11, 19, 8, 25, 14), "todo", "Send it", T("AM-12"), checkbox=True, due=date(2026, 11, 25)
        )
        line = entry.format()
        self.assertEqual(line, "- [ ] 2026-11-19 8:25:14 #AM-12 #todo Send it 📅 2026-11-25")
        parsed = Entry.parse(line)
        self.assertEqual((parsed.topic, parsed.kind, parsed.message, parsed.due), (T("AM-12"), "todo", "Send it", entry.due))
        self.assertFalse(parsed.done)

    def test_parse_ticked_task_with_done_date(self):
        parsed = Entry.parse("- [x] 2026-11-19 08:25:14 #todo Ship 📅 2026-11-20 ✅ 2026-11-21")
        self.assertTrue(parsed.done)
        self.assertIsNone(parsed.topic)
        self.assertEqual(parsed.message, "Ship")

    def test_topic_is_the_first_of_two_leading_tags(self):
        with_topic = Entry.parse("- 2026-11-19 8:25:14 #aq1/theseus #idea #later Seal it")
        without_topic = Entry.parse("- 2026-11-19 8:25:14 #idea Seal it")
        self.assertEqual((with_topic.topic, with_topic.kind, with_topic.message), (T("aq1/theseus"), "idea", "#later Seal it"))
        self.assertEqual((without_topic.topic, without_topic.kind), (None, "idea"))

    def test_topic_spaces_become_hyphens(self):
        self.assertEqual(str(T("#my project//field trial/")), "my-project/field-trial")
        self.assertIsNone(T("#/"))

    def test_parse_ignores_other_lines(self):
        self.assertIsNone(Entry.parse("- plain bullet"))
        self.assertIsNone(Entry.parse("## Notes"))

    def test_parse_day(self):
        monday = date(2026, 11, 23)
        self.assertEqual(parse_day("fri", monday), date(2026, 11, 27))
        self.assertEqual(parse_day("monday", monday), date(2026, 11, 30))
        self.assertEqual(parse_day("+3d", monday), date(2026, 11, 26))
        self.assertEqual(parse_day("2026-12-01", monday), date(2026, 12, 1))
        with self.assertRaises(ValueError):
            parse_day("someday", monday)

    def test_ticket_keys_restrict_matches(self):
        self.assertEqual(TicketKey.find_all("UTF-8 and AM-3 and SE-4 AM-3", ticket_pattern(["AM"])), [K("AM-3")])

    def test_ticket_key_and_selector(self):
        self.assertEqual(str(K("am-012")), "AM-12")
        with self.assertRaises(ValueError):
            K("aq1")
        self.assertEqual(parse_selector("am-3", ANY_TICKET), K("AM-3"))
        self.assertEqual(parse_selector("#aq1/x/", ANY_TICKET), T("aq1/x"))
        self.assertIsNone(parse_selector("", ANY_TICKET))


class SectionTest(unittest.TestCase):
    def test_adds_missing_section(self):
        self.assertEqual(insert_into_section("# Day\n\n", "Log", "- a"), "# Day\n\n## Log\n- a\n")

    def test_appends_inside_section_before_next_heading(self):
        text = "## Log\n- a\n\n## Notes\n- n\n"
        self.assertEqual(insert_into_section(text, "Log", "- b"), "## Log\n- a\n- b\n\n## Notes\n- n\n")

    def test_skips_headings_in_code_fences(self):
        text = "```\n## Log\n```\n"
        self.assertEqual(insert_into_section(text, "Log", "- a"), "```\n## Log\n```\n\n## Log\n- a\n")


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.config = Config(journal=root / "Journal", state=root / "state.json")

    def tearDown(self):
        self.directory.cleanup()

    def test_new_day_file_from_templater_template(self):
        template = Path(self.directory.name) / "daily.md"
        template.write_text("---\ndate: <% tp.date.now() %>\n---\n\n## Notes\n")
        self.config.template = template
        path = append_entry(self.config, Entry(datetime(2026, 11, 19, 8, 0, 0), "note", "hi"))
        self.assertEqual(path.read_text(), "---\ndate: 2026-11-19\n---\n\n## Notes\n\n## Log\n- 2026-11-19 8:00:00 #note hi\n")

    def test_read_entries_recurses_and_sorts(self):
        archived = self.config.journal / "2026-10" / "2026-10-01.md"
        archived.parent.mkdir(parents=True)
        archived.write_text("- 2026-10-01 9:00:00 #a/b #idea old\n")
        append_entry(self.config, Entry(datetime(2026, 11, 19, 8, 0, 0), "note", "new"))
        self.assertEqual([entry.message for entry in read_entries(self.config.journal)], ["old", "new"])


class RegistryTest(unittest.TestCase):
    def test_project_from_topic_prefix_then_ticket_mapping(self):
        registry = Registry(projects={T("aq1/theseus"): NOW, T("aq1/am100"): NOW}, tickets={K("AM-1"): T("aq1/am100")})
        by_topic = Entry(NOW, "note", "x", T("aq1/theseus/firmware"))
        by_ticket = Entry(NOW, "commit", "AM-1 Fix it", None)
        orphan = Entry(NOW, "note", "x", T("SE-9"))
        self.assertEqual(registry.project_of(by_topic, ANY_TICKET), T("aq1/theseus"))
        self.assertEqual(registry.path_of(by_ticket, ANY_TICKET), T("aq1/am100/AM-1"))
        self.assertIsNone(registry.project_of(orphan, ANY_TICKET))

    def test_filter_by_ticket_and_path(self):
        registry = Registry(projects={T("p"): NOW}, tickets={K("AM-1"): T("p")})
        rows = views.resolve(
            [Entry(NOW, "note", "a", T("AM-1")), Entry(NOW, "note", "b", T("q/x"))], registry, ANY_TICKET
        )
        self.assertEqual([row.entry.message for row in views.filter_rows(rows, selector=T("p"))], ["a"])
        self.assertEqual([row.entry.message for row in views.filter_rows(rows, selector=K("am-1"))], ["a"])
        self.assertEqual([row.entry.message for row in views.filter_rows(rows, selector=T("q"))], ["b"])
        self.assertEqual([row.entry.message for row in views.filter_rows(rows, unassigned=True)], ["b"])


class RegistryEditTest(unittest.TestCase):
    def test_register_assign_remove_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            with edit_registry(path) as registry:
                self.assertTrue(registry.assign(K("AM-1"), T("p")))
                self.assertFalse(registry.register(T("p")))
                registry.unassign(K("AM-2"))
            loaded = load_registry(path)
            self.assertEqual(loaded.tickets, {K("AM-1"): T("p"), K("AM-2"): None})
            with edit_registry(path) as registry:
                self.assertTrue(registry.remove(T("p")))
                self.assertFalse(registry.remove(T("p")))
            self.assertEqual(load_registry(path).tickets[K("AM-1")], None)


class NoteTopicTest(unittest.TestCase):
    def test_split_topic(self):
        registry = Registry(projects={T("logbook"): NOW})
        cases = {
            ("aq1/theseus", "Use a gasket"): ("aq1/theseus", "Use a gasket"),
            ("#aq1/theseus", "Use", "a", "gasket"): ("aq1/theseus", "Use a gasket"),
            ("AM-12", "done"): ("AM-12", "done"),
            ("logbook", "done"): ("logbook", "done"),
            ("fix", "the", "thing"): (None, "fix the thing"),
            ("Ask about #aq1/xbee range",): ("aq1/xbee", "Ask about #aq1/xbee range"),
        }
        for words, expected in cases.items():
            self.assertEqual(cli.split_topic(list(words), registry, ANY_TICKET), (T(expected[0] or ""), expected[1]))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.config_path = root / "config.toml"
        self.config_path.write_text(f'journal = "{root / "Journal"}"\nstate = "{root / "state.json"}"\n')

    def tearDown(self):
        self.directory.cleanup()

    def run_logbook(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            cli.logbook_main(["--config", str(self.config_path), *arguments])
        return output.getvalue()

    def test_idea_and_decision_aliases(self):
        with redirect_stdout(io.StringIO()):
            cli.idea_main(["--config", str(self.config_path), "#aq1/x", "Use", "a", "gasket"])
            cli.decision_main(["--config", str(self.config_path), "AM-3", "Keep the SDK"])
        rows = json.loads(self.run_logbook("show", "--json"))
        self.assertEqual([(row["kind"], row["topic"], row["message"]) for row in rows],
                         [("idea", "aq1/x", "Use a gasket"), ("decision", "AM-3", "Keep the SDK")])
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            cli.idea_main(["--due", "fri", "x"])

    def test_note_assign_and_json_view(self):
        with redirect_stdout(io.StringIO()):
            cli.note_main(["--config", str(self.config_path), "--due", "tomorrow", "AM-7", "Write", "docs"])
        self.assertEqual(json.loads(self.run_logbook("tickets", "--unassigned", "--json"))[0]["name"], "AM-7")
        self.run_logbook("assign", "am-7", "aq1/logbook")
        rows = json.loads(self.run_logbook("show", "aq1/logbook", "--open", "--json"))
        self.assertEqual((rows[0]["path"], rows[0]["kind"], rows[0]["message"]), ("aq1/logbook/AM-7", "todo", "Write docs"))
        self.assertIn("aq1/logbook/AM-7", self.run_logbook("show", "--no-colour"))
        self.assertEqual(json.loads(self.run_logbook("tickets", "--unassigned", "--json")), [])


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.config = Config(journal=root / "Journal", state=root / "state.json")
        self.repo = root / "widget"
        environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        self.git = lambda *arguments: subprocess.run(
            ["git", "-C", str(self.repo), *arguments], check=True, capture_output=True, env=environment
        )
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
                 "commit", "-q", "--allow-empty", "-m", "AM-5 Add the widget")

    def tearDown(self):
        self.directory.cleanup()

    def test_commit_topic_from_subject_ticket(self):
        entry = commit_entry(self.config, self.repo)
        self.assertEqual(entry.topic, T("AM-5"))
        self.assertRegex(entry.message, r"^AM-5 Add the widget \(widget@main [0-9a-f]+\)$")

    def test_new_branch_only(self):
        self.git("checkout", "-q", "-b", "AM-6-thing")
        entry = branch_entry(self.config, self.repo, True)
        self.assertEqual((entry.topic, entry.message), (T("AM-6"), "Created AM-6-thing in widget from HEAD"))
        self.assertIsNone(branch_entry(self.config, self.repo, False))
        self.git("checkout", "-q", "main")
        self.assertIsNone(branch_entry(self.config, self.repo, True))

    def test_nvim_skips_journal_and_groups_by_repo(self):
        source = self.repo / "a.py"
        source.write_text("")
        self.config.journal.mkdir()
        day = self.config.journal / "2026-11-23.md"
        day.write_text("")
        entries = nvim_entries(self.config, self.repo, [source, day], started=datetime(2026, 1, 1))
        self.assertEqual(len(entries), 1)
        self.assertRegex(entries[0].message, r"^Edited 1 file in widget@main over \d+h \d\dm: a.py$")


class ConfigTest(unittest.TestCase):
    def test_missing_journal_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text("")
            previous = os.environ.pop("LOGBOOK_JOURNAL", None)
            try:
                with self.assertRaises(Exception):
                    load_config(path)
            finally:
                if previous is not None:
                    os.environ["LOGBOOK_JOURNAL"] = previous


if __name__ == "__main__":
    unittest.main()
