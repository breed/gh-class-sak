# gh-class-sak

**Manage a whole course's GitHub repos from the command line — now that GitHub Classroom
is gone.**

[![CI](https://github.com/breed/gh-class-sak/actions/workflows/ci.yml/badge.svg)](https://github.com/breed/gh-class-sak/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gh-class-sak)](https://pypi.org/project/gh-class-sak/)
[![Python](https://img.shields.io/pypi/pyversions/gh-class-sak)](https://pypi.org/project/gh-class-sak/)
[![License](https://img.shields.io/pypi/l/gh-class-sak)](LICENSE)

![Terminal demo: gh-class-sak listing classrooms, showing an assignment's teams and members, and previewing a bulk clone for grading](https://raw.githubusercontent.com/breed/gh-class-sak/main/docs/demo.svg)

A GitHub org hosts your **classrooms**, described by one small versioned state repo:
[`classroom-meta`](docs/commands.md#the-classroom-meta-repo) — a directory per classroom,
a hand-editable tsv file per **assignment**, a row per **team**. Everything else is
derived from it and the repo names:

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

Pull every team's repo down for grading — safe by default, so this only *previews*:

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
```

Add `--no-dryrun` and it actually clones, fast-forwarding any repo you already have.

## What it does

- **One versioned state repo per org** — classrooms are directories, assignments are tsv
  files you can hand-edit, diff, and review; an org hosts as many classrooms as you need
- **Roster tables built for the shell** — teams, members, instructors, real names, and
  the emails students actually commit with, in columns that `cut` and `awk` parse
- **Bulk clone for grading** — clone or fast-forward every team's repo into one
  directory, named by team
- **Canvas integration** — map orgs to Canvas courses for rosters, group matching,
  per-section instructor columns, and "who has no repo yet" reports
- **Managed classrooms** — `meta apply` reconciles the org to the
  [classroom-meta repo](docs/commands.md#the-classroom-meta-repo): creates private repos
  (optionally from a template), keeps student, TA, and branch-protection state exactly as
  recorded, and tracks repos by permanent id so renames can't hide them
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

- **[Getting started](docs/getting-started.md)** — install, tokens, the Canvas config,
  and a first walk through a course
- **[Migrating from GitHub Classroom](docs/migrating-from-github-classroom.md)** —
  where Classroom's bookkeeping lives now, and the one-command import
- **[Commands](docs/commands.md)** — the full reference: every command, every flag, and
  the classroom-meta repo

Every example on those pages — and above — is replayed against an invented demo course by
the test suite, so the output you see is the output you get.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The test suite stubs out GitHub and Canvas, so you
can contribute without a course, a token, or a Canvas account:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Security policy: [SECURITY.md](SECURITY.md). Please report vulnerabilities privately.
