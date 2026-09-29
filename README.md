# gh-class-sak

**Manage a whole course's GitHub repos from the command line — now that GitHub Classroom
is gone.**

The name says what it is: **gh** for GitHub, **class** for the class you teach, and
**SAK** for Swiss Army Knife — one command-line tool with a blade for each course-repo
chore: setting up repos, keeping access in line, listing, cloning for grading, and
chasing students on Canvas.

[![CI](https://github.com/breed/gh-class-sak/actions/workflows/ci.yml/badge.svg)](https://github.com/breed/gh-class-sak/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gh-class-sak)](https://pypi.org/project/gh-class-sak/)
[![Python](https://img.shields.io/pypi/pyversions/gh-class-sak)](https://pypi.org/project/gh-class-sak/)
[![License](https://img.shields.io/pypi/l/gh-class-sak)](https://github.com/breed/gh-class-sak/blob/main/LICENSE)
[![Discord](https://img.shields.io/badge/discord-join%20the%20server-5865F2?logo=discord&logoColor=white)](https://discord.gg/nyfCHTZJkt)

![Terminal demo: gh-class-sak listing courses, showing an assignment's teams and members, and previewing a bulk clone for grading](https://raw.githubusercontent.com/breed/gh-class-sak/main/docs/demo.svg)

Three words cover the whole tool:

- a **course** is one Canvas course, hosted in a GitHub org (an org can host several)
- an **assignment** is one repo per student or group in a course: assignment `hw1`
  gives repos like `hw1-jdoe`, `hw1-rpatel`
- a **team** is the student or group behind one of those repos

They're recorded in one small versioned state repo in the org,
[`classroom-meta`](https://github.com/breed/gh-class-sak/blob/main/docs/commands.md#the-classroom-meta-repo) — a directory per course,
a hand-editable tsv file per assignment, a row per team. Everything else is derived
from it and the repo names:

```console
$ gh-class-sak course list --org cs101-fall
scanning cs101-fall ...
COURSE      PREFIX  TAS  ASSIGNMENTS
cs101_fall  -       0    hw1(2) project(3)
```

With your org listed in the config file (`gh-class-sak help-me-setup` shows how),
setting a course up is three commands — record the course, create an assignment's
repos, and sync whenever something changes:

```bash
gh-class-sak course init CS-101 --no-dryrun
gh-class-sak assignment create CS-101 hw1 --from-canvas --no-dryrun
gh-class-sak sync CS-101 --no-dryrun
```

List the teams on an assignment, with their members and real names:

```console
$ gh-class-sak repos list cs101-fall project --members --name
TEAM       MEMBERS
team-1     jdoe(Jane Doe),msmith(Marcus Smith)
nightowls  rpatel(Riya Patel),tk-codes
team-3     lchen(Lin Chen)
```

Pull every team's repo down for grading — safe by default, so this only *previews*:

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  dry run: no changes will be made. add --no-dryrun to apply
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
```

Add `--no-dryrun` and it actually clones, fast-forwarding any repo you already have.

## What it does

- **One versioned state repo per org** — courses are directories, assignments are tsv
  files you can hand-edit, diff, and review; an org hosts as many courses as you need
- **Roster tables built for the shell** — teams, members, instructors, real names, and
  the emails students actually commit with, in columns that `cut` and `awk` parse
- **Bulk clone for grading** — clone or fast-forward every team's repo into one
  directory, named by team
- **Canvas integration** — map orgs to Canvas courses: build an assignment's repos
  straight from the enrollment roster or a Canvas group set (one repo per person or
  per group), resolve emails to GitHub ids via Canvas profile links, match groups,
  add per-section instructor columns, and report who has no repo yet
- **Message the stragglers** — `canvas message-missing` finds every student stranded
  on the way to their repo — no GitHub link on their Canvas profile, a broken one, or
  a repo invitation they never accepted — and sends each a Canvas message saying
  exactly what to fix; a dry run shows every message before anything goes out
- **Managed courses** — `sync` makes the org match the
  [classroom-meta repo](https://github.com/breed/gh-class-sak/blob/main/docs/commands.md#the-classroom-meta-repo): creates private repos
  (optionally from a template), grants student, TA, and branch-protection state exactly
  as recorded — removing people is opt-in — and tracks repos by permanent id so renames
  can't hide them
- **Safe by default** — every mutating command previews with a ⚠️ until you pass
  `--no-dryrun`, and your token never appears in `ps` output, clone URLs, or
  `.git/config`

## Installation

```bash
pip install gh-class-sak
```

Or, to keep it out of your project environments:

```bash
pipx install gh-class-sak      # or: uv tool install gh-class-sak
```

Requires Python 3.9+.

## Documentation

- **[Getting started](https://github.com/breed/gh-class-sak/blob/main/docs/getting-started.md)** — install, tokens, the Canvas config,
  and a first walk through a course
- **[Migrating from GitHub Classroom](https://github.com/breed/gh-class-sak/blob/main/docs/migrating-from-github-classroom.md)** —
  where Classroom's bookkeeping lives now, and the one-command import
- **[Canvas integration](https://github.com/breed/gh-class-sak/blob/main/docs/canvas-integration.md)** — how GitHub ids map to Canvas
  accounts, assignments built from enrollments or group sets, and messaging the
  students whose setup is stuck
- **[The classroom-meta files](https://github.com/breed/gh-class-sak/blob/main/docs/classroom-meta-files.md)** — the file layouts and
  formats, and how TA teams manage the TAs
- **[Commands](https://github.com/breed/gh-class-sak/blob/main/docs/commands.md)** — the full reference: every command, every flag, and
  the classroom-meta repo

Every example on those pages — and above — is replayed against an invented demo course by
the test suite, so the output you see is the output you get.

## Contributing

Questions, war stories, and quick help live on the
[Discord server](https://discord.gg/nyfCHTZJkt) — running a course with this, or thinking
about it? Come say hi.

See [CONTRIBUTING.md](https://github.com/breed/gh-class-sak/blob/main/CONTRIBUTING.md). The test suite stubs out GitHub and Canvas, so you
can contribute without a course, a token, or a Canvas account:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Security policy: [SECURITY.md](https://github.com/breed/gh-class-sak/blob/main/SECURITY.md). Please report vulnerabilities privately.
