# Auto logbook
This repo contains a collection of tools that automate collecting progress logs, tagged by time and
grouped by project, topic, or ticket.

These logs are gathered from actions that are already done or documentation already written, such as
git branches and commits, claude sessions, Jira ticket updates, or obsidian file updates.

There is also an option to add one with `log --due [date] [topic] <message>`

## The log
The log contains a list of messages in a human readable format, including information like date,
time, heirarchical topic (eg. a project name, ticket, or domain - see the tags in the `~/personal/`
obsidian vault). Mutated programmatically relying on a structure, eg.

```text
# general note eg. by calling `note "project_name/topic" --idea "<Note content>"`, 
# or idea #project_name/topic Note content
- 2026-11-19 8:25:14 #project_name/topic #(idea|decision) <Note content>
# similar for a to do
- [ ] 2026-11-19 8:25:14 #project_name/topic #todo <Note content>
```
Group files by day, in a central location (eg. `~/personal/Journal`)

## Capture domains
- a command line tool for manual creation
- Hooks into branch creation and commits through global git hooks (by setting `core.hooksPath`)
- nvim sessions through an on-close autocommand
- claude skill describing what to do when asked to summarise a session, including what level of
  summarisation is appriopriate, and what kinds of things warrant being summarised (start with a
  high level summary, one oneliner per well defined topic, mirroring the wording of the initial
  prompt/prompts).

## What projects exist
- projects are created by a cli command, log sources are linked to projects by grouping information.
  - Tickets are assigned projects, where they don't get assigned, they can be linked into projects
    in post through a retroactive mapping for ticket->project.
  - Commits and manual notes mention tickets, or projects (#<project>/) or get no project.

## Views
- Command line tools provide views to project/subtype, pretty printed to the console, with options
  for `no-colour` and `json` output
- Items/Tickets/projects can be viewed, filtered and un/assigned in a simple tui, with special views
  for unassigned tickets.
