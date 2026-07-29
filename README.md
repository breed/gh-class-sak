# gh-class-sak

**Manage a whole course's GitHub repos from the command line — now that GitHub Classroom
is gone.**

[![CI](https://github.com/breed/gh-class-sak/actions/workflows/ci.yml/badge.svg)](https://github.com/breed/gh-class-sak/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gh-class-sak)](https://pypi.org/project/gh-class-sak/)
[![Python](https://img.shields.io/pypi/pyversions/gh-class-sak)](https://pypi.org/project/gh-class-sak/)
[![License](https://img.shields.io/pypi/l/gh-class-sak)](LICENSE)

A **classroom** is just a GitHub org. An **assignment** is the repo-name prefix its repos
share. A **team** is whatever follows that prefix. Nothing else is required — no Classroom
API, no per-assignment bookkeeping, no state file. Point it at an org and it works out the
rest from the repo names:

```console
$ gh-class-sak classrooms cs101-fall
scanning cs101-fall ...
cs101-fall: hw1
cs101-fall: project
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

Optionally, wire in Canvas to get rosters, group matching, and which TA is responsible for
which team.

## Installation

```bash
pip install gh-class-sak
```

Or, to keep it out of your project environments:

```bash
pipx install gh-class-sak      # or: uv tool install gh-class-sak
```

Requires Python 3.9+.

## Authentication

### GitHub

Your GitHub token, resolved in this order:

1. `GH_TOKEN` environment variable
2. `gh auth token` (GitHub CLI)

### Config file (optional)

Without a config file, pass the org name directly as the classroom argument and everything
except the Canvas features works. The config is required for `--group`, `--instructors`,
`--email`, and `repos missing`.

Its location follows the platform convention: `~/.config/gh-class-sak.ini` on Linux,
`~/Library/Application Support/gh-class-sak.ini` on macOS, and `%APPDATA%\gh-class-sak.ini`
on Windows. When a command that needs the config can't find it, the error prints the exact
path.

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
and `cs101-fall` resolve to the same org. Matching is case-insensitive and treats hyphens,
underscores, and spaces as equivalent.

Several Canvas courses may map to one org — two sections sharing a repo home is normal. In
that case name the course (`195A`), not the org, so the Canvas lookups know which one you
mean.

> ⚠️ The config file holds your Canvas API token in plain text. Keep it readable only by
> you.

## Usage

### classrooms

List the assignments detected in a classroom. Pass the org (or a course name from the
config) as the argument; with no argument, every org mapped in the `[COURSES]` section
of the config is listed. Orgs are never discovered from your token — your account may
belong to orgs with thousands of unrelated repos, and scanning them would take forever.

Assignments are inferred as any `-` delimited repo-name prefix shared by two or more
repos, with sub-patterns of a broader assignment suppressed — so `project-team-1` and
`project-nightowls` yield `project`, not also `project-team`.

```console
$ gh-class-sak classrooms cs101-fall
scanning cs101-fall ...
cs101-fall: hw1
cs101-fall: project
```

An assignment with only one repo won't be listed. You can still pass its prefix to the
other commands.

### repos list

List the repos for an assignment. Both arguments accept partial names.

```
gh-class-sak repos list CLASSROOM ASSIGNMENT [OPTIONS]
```

| Option | Effect |
|---|---|
| `--repo` | show the full repo name (`owner/repo`) |
| `--members` | show the members column — collaborators, excluding admins |
| `--instructors` | show the instructors column, matched via shared Canvas course sections |
| `--name` | annotate members and instructors with their profile names |
| `--email` | annotate them with emails, preferring the address from commit history |
| `--group CATEGORY` | match repos to a Canvas group category by fuzzy-matching member names |
| `--show-empty` | include teams with no members (hidden by default when `--members` is on) |

`--name` and `--email` annotate an existing column, so pair them with `--members` or
`--instructors`.

```console
$ gh-class-sak repos list cs101-fall project --repo --members
TEAM       REPO                          MEMBERS
team-1     cs101-fall/project-team-1     jdoe,msmith
nightowls  cs101-fall/project-nightowls  rpatel,tk-codes
team-3     cs101-fall/project-team-3     lchen
```

Output is space-padded columns with the last column unpadded, so it stays readable in a
terminal and parseable with `cut`/`awk`.

### repos members

Every commit author per repo, mined from commit history. Addresses ending in
`@users.noreply.github.com` are skipped, and commits from someone with no linked GitHub
account show `?`.

```console
$ gh-class-sak repos members cs101-fall project
REPO       GITHUB_ID  NAME        EMAIL
team-1     jdoe       Jane Doe    jane.doe@cs101.edu
nightowls  rpatel     Riya Patel  riya@cs101.edu
```

This is the fastest way to find the email a student actually commits with, which is often
not the one on their Canvas profile.

### repos missing

Canvas students, or Canvas groups, with no repo for the assignment. Both modes need the
Canvas config.

```
gh-class-sak repos missing CLASSROOM ASSIGNMENT [--group CATEGORY]
```

Without `--group`, a student counts as missing when their GitHub id — taken from the
GitHub link on their Canvas profile — is not a collaborator on any repo, and their name
doesn't fuzzy-match any collaborator's profile name.

With `--group`, it lists Canvas groups that no repo could be matched to, along with their
members.

### repos clone

Clone every repo for an assignment into `--dest`, one directory per team, fast-forwarding
any that are already there.

```
gh-class-sak repos clone CLASSROOM ASSIGNMENT [--dest DIR] [--dryrun/--no-dryrun]
```

It writes to disk, so it previews by default and only acts with `--no-dryrun`:

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
```

Your token is handed to git through the environment, so it never appears in `ps` output,
in the clone URL, or in the checked-out `.git/config`.

## The meta repo

Prefix discovery works with nothing but naming conventions, but it can't survive a team
renaming their repo, and it knows nothing about who *should* have access. The `meta`
command group fixes both by keeping classroom state in a private repo named `meta` inside
the org — versioned, hand-editable, and invisible to students. An org can host several
classrooms (two Canvas sections often share one org); each is a directory:

```
meta/
  sp26_cmpe_195a/                  one directory per classroom
    classroom.ini                  [CLASSROOM] prefix, template, repo settings
    tas                            one github login or email per line
    students.tsv                   NAME  STUDENTS  REPO  REPO_ID
```

`students.tsv` is the heart of it. You supply the first two columns — `NAME` (the suffix
appended to the course prefix, so `team-1` becomes `PREFIX-team-1`) and `STUDENTS` (the
comma-joined emails or GitHub logins who get write access). The tool fills in the last two
when it creates the repo: the URL, and GitHub's **permanent numeric repo id** — which is
how a repo stays tracked even after students rename it.

### meta init

Create the meta repo and record a classroom. With a Canvas config, the `tas` file is
seeded from the course's TA and teacher enrollments. Like every mutating command, it
previews by default:

```console
$ gh-class-sak meta init cs101-fall --prefix project
no canvas config; seed the tas file by hand
⚠️  would create private cs101-fall/meta
⚠️  would record cs101_fall: prefix=project tas=-
```

### meta assign

Feed it your team table — just the two columns, emails and logins mixed freely:

```
NAME       STUDENTS
team-1     jane@sjsu.edu,msmith
nightowls  rpatel,tk-codes
```

```
gh-class-sak meta assign CLASSROOM teams.tsv [--dryrun/--no-dryrun]
```

Emails are resolved to GitHub logins via the student's Canvas profile link, then the
GitHub search API; an email nothing can resolve is a loud error. Under `--no-dryrun` it
creates each missing repo (privately, from the template when `classroom.ini` names one),
records the URL and repo id, and grants the listed students push. Re-importing an updated
table changes student lists but **never clobbers a recorded repo**.

### meta apply

Reconcile the org to match the meta repo:

```
gh-class-sak meta apply CLASSROOM [--dryrun/--no-dryrun]
```

Every classroom directory in the meta repo is reconciled:

- rows without a repo yet — including ones you hand-added to `students.tsv` — get created
- each classroom has its own **`<classroom>-tas` team** (e.g. `sp26_cmpe_195a-tas`) whose
  membership matches its `tas` file, added as a **read** collaborator on each of that
  classroom's student repos — so TAs accept one org invite ever, and TAs of one classroom
  never gain access to another classroom's repos
- every listed student has **write** on their repo; non-admin collaborators who aren't
  listed are revoked — org admins are never touched
- every recorded repo's default branch carries the classroom's protection settings
- run it twice: the second pass prints `nothing to do`

### Repo settings

`classroom.ini` can also carry branch-protection settings for the classroom's repos:

```
[CLASSROOM]
prefix = project
protection = pr-review     # none (default) or pr-review: require one approving review
linear_history = true      # default true: require a linear history
force_push = false         # default false: block force pushes
```

`meta assign` and `meta apply` put the effective settings on each repo's default branch —
at creation for repos made from a template, and on the next `meta apply` after the first
push for repos created empty (GitHub can't protect a branch that doesn't exist yet).
`meta apply` also repairs drift on every recorded repo, checking first so an untouched org
still reconciles to `nothing to do`.

Two caveats: GitHub can't protect private repos on a free org plan — the tool warns and
moves on — and a protection write replaces the whole protection object, so hand-set extras
like required status checks don't survive it. The all-off trio (`protection = none`,
`linear_history = false`, `force_push = true`) asks for nothing and skips the protection
API entirely; existing protection is never removed.

### meta show

Print a classroom's recorded state: prefix, template, TAs, effective repo settings, and
the full assignment table.

Once repos are recorded, `repos list`, `repos members`, `repos missing`, and `repos clone`
all include them by id — so a renamed repo shows up under its original team name instead
of silently vanishing.

## How group matching works

With `--group`, the tool:

1. Fetches Canvas groups and their members from the mapped course
2. Fetches GitHub repo collaborator profile names
3. Fuzzy-matches names between Canvas and GitHub — handles "Last, First", uses a
   similarity threshold, so `Adams, Alice` matches `Alice Adams`
4. Assigns groups globally, highest-scoring pair first, so each Canvas group maps to at
   most one repo

Unmatched repos show `?` in the GROUP column. That usually means nobody on the team put
their real name on their GitHub profile.

## Known limitations

- **Renamed repos are invisible to prefix discovery alone.** If a team renames
  `project-widgets` to `widgets` it drops out of listings — unless the repo is recorded in
  the [meta repo](#the-meta-repo), which tracks repos by their permanent id and survives
  any rename.
- Students are matched to Canvas by fuzzy name comparison, not by ID. A student whose
  GitHub profile has no real name can't be matched.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The test suite stubs out GitHub and Canvas, so you
can contribute without a course, a token, or a Canvas account:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Security policy: [SECURITY.md](SECURITY.md). Please report vulnerabilities privately.
