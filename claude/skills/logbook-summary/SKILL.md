---
name: logbook-summary
description: Summarise the current Claude Code session into the logbook journal with the `note` command. Use when asked to summarise, log, journal or record this session or what was done in it.
---

# Summarise a session into the logbook

The logbook is a daily journal of one-line entries. `note` writes an entry to
today's day file. Every line written here is read later, cold, by the user
scanning a week of work. Write for that reader.

## What goes in

Write one entry for each of these that the session produced:

- **Work done**: something built, changed, fixed or configured.
- **Finding**: a cause found, a question answered, a measurement taken.
- **Decision**: a choice between options that changes the design, the spec or
  the device. Use `decision`, or `note --decision`.
- **Idea**: something proposed for later and not done. Use `idea`, or `note --idea`.
- **Follow-up**: work that the session named and did not finish. Use `--todo`,
  with `--due` only when the user gave a date.

Leave out:

- Tool calls, file reads, commands run and other process.
- Attempts that failed, unless the failure is itself a finding.
- Lookups and explanations that changed nothing.
- Anything the git hooks already record, such as the commit subjects.

## How much to write

1. Start with **one high-level summary** of the session as a `--kind claude`
   entry. Mirror the wording of the user's first prompt, so the entry is found by
   the same words the user would search for.
2. Then write **one one-liner per well-defined topic** the session covered.
   Mirror the wording of the prompt that started that topic.
3. A session about one topic gets the summary line only. Do not split one topic
   into several lines.
4. A line is one sentence. State the outcome, not the steps.

## Topic

Pass the topic as the first argument. Pick the first that applies:

1. A ticket key the session worked on, such as `AM-123`. Look in the branch name
   with `git branch --show-current`.
2. A registered project and subtopic, such as `aq1/theseus/firmware`. List the
   projects with `logbook projects`.
3. No topic. Do not invent a project name.

## Commands

```sh
note --kind claude AM-123 "Added ticket assignment to the logbook TUI"
note AM-123 "Found the nvim hook did not run under lazy.nvim, plugin moved to site"
decision aq1/theseus/firmware "Keep the bootloader on the 2025 SDK"
idea aq1/theseus "Log Jira transitions as entries"
note --todo --due fri AM-123 "Write the install section of the README"
```

Quote each message. Run the commands, then show the user the lines `note`
printed. Do not ask for approval first unless the user asked to review the
summary.
