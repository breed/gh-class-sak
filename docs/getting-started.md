# Getting started

This walk-through takes you from an empty shell to a recorded classroom, browsing a
course, and wiring in Canvas. Every `console` example is replayed against an invented
demo course by the test suite, so the output shown is real.

## Install

```bash
pip install gh-class-sak
```

Or, to keep it out of your project environments:

```bash
pipx install gh-class-sak      # or: uv tool install gh-class-sak
```

Requires Python 3.9+.

## Authentication

Your GitHub token is resolved in this order:

1. `GH_TOKEN` environment variable
2. `gh auth token` (GitHub CLI)

If you already use the `gh` CLI, there is nothing to set up.

## Naming your classroom: the org and the config file

Every command takes a `CLASSROOM` argument, and it names a **GitHub org**. With no
config file, the argument *is* the org name, verbatim — `gh-class-sak classrooms
cs101-fall` works the moment your token can see the `cs101-fall` org.

A config file makes that argument friendlier and unlocks the Canvas features. Its
location follows the platform convention: `~/.config/gh-class-sak.ini` on Linux,
`~/Library/Application Support/gh-class-sak.ini` on macOS, and
`%APPDATA%\gh-class-sak.ini` on Windows. When a command that needs the config can't find
it, the error prints the exact path.

```ini
[CANVAS]
url = https://your-canvas-instance.instructure.com
token = YOUR_CANVAS_API_TOKEN

[COURSES]
CS-101 = cs101-fall
CS-210A = cs210-org
```

`[COURSES]` maps a Canvas course name partial (key) to a **GitHub org** (value). The
classroom argument matches either side, so with the config above all of `101`, `CS-101`,
and `cs101-fall` resolve to the same org — you type the course name you know, not the
org GitHub knows. Matching is case-insensitive and treats hyphens, underscores, and
spaces as equivalent. With no argument at all, `classrooms` lists every org mapped here.

Several Canvas courses may map to one org — two sections sharing a repo home is normal.
In that case name the course (`195A`), not the org, so the Canvas lookups know which one
you mean.

The `[CANVAS]` section unlocks the roster features — `--group`, `--instructors`,
`--email`, and `repos missing` — and lets `meta init` seed the TA list and `meta assign`
resolve student emails from the course roster.

> ⚠️ The config file holds your Canvas API token in plain text. Keep it readable only by
> you.

## Record your classroom

A GitHub org hosts your **classrooms**. Each one is a directory in the org's private
[classroom-meta repo](commands.md#the-classroom-meta-repo) — a small versioned state repo
that every other command reads. Inside a classroom directory, each `.tsv` file is an
**assignment**, and each row of it is a **team**.

`meta init` creates the classroom-meta repo when the org doesn't have one yet, and
records a classroom in it. Mutating commands are safe by default — they *preview* with a
⚠️ until you add `--no-dryrun`:

```console
$ gh-class-sak meta init cs101-fall
no canvas config; seed the tas file by hand
⚠️  would record cs101_fall: prefix=- tas=-
```

Then feed `meta assign` your team table — emails and logins mixed freely, the file's
basename names the assignment:

```
NAME       STUDENTS
team-1     jane@sjsu.edu,msmith
nightowls  rpatel,tk-codes
```

```bash
gh-class-sak meta assign cs101-fall project.tsv --no-dryrun
```

It creates each repo privately (from a template, if the classroom names one), grants the
students push, and records the repo's URL and permanent id — so even a renamed repo stays
tracked. From then on, `meta apply` reconciles everything: missing repos, student access,
the classroom's TA team, and branch protection. Run it twice — the second pass prints
`nothing to do`.

## Browse the course

With the classroom recorded, point any command at the org — or at a course name from
your `[COURSES]` mapping:

```console
$ gh-class-sak classrooms cs101-fall
scanning cs101-fall ...
cs101_fall: hw1
cs101_fall: project
```

List the teams on an assignment, with their members and real names:

```console
$ gh-class-sak repos list cs101-fall project --members --name
TEAM       MEMBERS
team-1     jdoe(Jane Doe),msmith(Marcus Smith)
nightowls  rpatel(Riya Patel),tk-codes
team-3     lchen(Lin Chen)
```

Pull every team's repo down for grading — like all mutating commands, a preview until
`--no-dryrun`:

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
```

Add `--no-dryrun` and it actually clones, fast-forwarding any repo you already have.

## Where to next

- **[Commands](commands.md)** — the full reference: every command, every flag, and the
  classroom-meta repo in detail
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — the test suite stubs GitHub and Canvas, so
  you can hack on the tool without a course or a token
