# Getting started

This walk-through takes you from an empty shell to a recorded course with its repos, browsing it,
and wiring in Canvas. Every `console` example is replayed against an invented
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

Whichever it is, the token has to be able to see **private** repos in the org: the
`classroom-meta` repo is private, and GitHub answers "not yours to see" with the same
404 it uses for "not there". So a classic token needs the `repo` scope
(`gh auth refresh -h github.com -s repo`); a fine-grained token needs the org as one of
its resource owners, with Contents: read approved by an org owner; and an org that
enforces SAML SSO needs the token authorized for it. When a command reports
`no classroom-meta repo visible in "ORG"`, it also prints which of these the token looks
like — that message means "absent **or** invisible", not "the course isn't set up".

## The words: course, assignment, team

- A **course** is one Canvas course. It lives in a **GitHub org**, and one org can host
  several courses.
- An **assignment** is one repo per student or group in a course: assignment `hw1`
  gives repos like `hw1-jdoe` and `hw1-rpatel` (with the course's prefix in front, when
  it has one).
- A **team** is the student or group behind one of those repos — the repo name with
  the assignment's prefix stripped off.

Commands that act on a course take a `COURSE` argument; `--org` names the GitHub org
when the tool can't tell it from your config.

## The config file

A config file lists your orgs and, optionally, your Canvas credentials. Its location
follows the platform convention: `~/.config/gh-class-sak.ini` on Linux,
`~/Library/Application Support/gh-class-sak.ini` on macOS, and
`%APPDATA%\gh-class-sak.ini` on Windows. When a command that needs the config can't find
it, the error prints the exact path.

```ini
[ORGS]
cs101-fall
cs210-org

[CANVAS]
url = https://your-canvas-instance.instructure.com
token = YOUR_CANVAS_API_TOKEN
```

`[ORGS]` lists the GitHub orgs hosting your courses, one per line — the course list
itself lives in each org's classroom-meta repo, not in the config. With orgs
configured, a `COURSE` argument is looked up in all of them, so you never need
`--org`: courses are directories named after the Canvas course, and `101`, `CS-101`,
and `cs101_fall` all find the same one. Matching is case-insensitive and treats
hyphens, underscores, and spaces as equivalent; an exact name beats a partial one, and
an ambiguous name is an error listing the candidates. Without a config, pass `--org`.

The `[CANVAS]` section unlocks the roster features — `--group`, `--instructors`,
`--email`, and `repos missing` — and lets `course init` seed the TA list and
`assignment create` build its roster from Canvas or resolve student emails. The full
story — how GitHub ids map to Canvas accounts, and building assignments straight from
enrollments or group sets — is in [Canvas integration](canvas-integration.md).

> ⚠️ The config file holds your Canvas API token in plain text. Keep it readable only by
> you.

When in doubt, ask the tool itself:

```bash
gh-class-sak help-me-setup
```

It explains the config file (printing a template when none exists) and verifies the
whole setup: the GitHub token, each configured org and its classroom-meta repo, and
the Canvas credentials.

## Set up a course: three commands

Everything the tool knows lives in the org's private
[classroom-meta repo](commands.md#the-classroom-meta-repo) — a small versioned state repo
that every other command reads. Each course is a directory in it; each assignment is a
`.tsv` file in that directory, one row per team. Mutating commands are safe by
default — they *preview* with a ⚠️ until you add `--no-dryrun`.

**1. Record the course.** `course init` creates the classroom-meta repo when the org
doesn't have one yet, and records the course in it. The org is the single configured
`[ORGS]` entry — with several orgs configured, or none, pass `--org` (partial names
work):

```console
$ gh-class-sak course init CS-101 --org cs101-fall
⚠️  dry run: no changes will be made. add --no-dryrun to apply
no canvas config; seed the [TAS] section by hand
⚠️  would record cs_101: prefix=CS-101 tas=-
⚠️  would create team "cs_101-TAs" in cs101-fall
```

**2. Create an assignment's repos.** `assignment create` takes the course, the
assignment's name, and its roster — straight from Canvas with `--from-canvas`, or a
table you wrote with `--roster`. Identities are `EMAIL/GITHUBID`, with either half
omissible (`jane@sjsu.edu/`, `/msmith`):

```
NAME       STUDENTS
team-1     jane@sjsu.edu/,/msmith
nightowls  /rpatel,/tk-codes
```

```bash
gh-class-sak assignment create CS-101 project --roster project.tsv --no-dryrun
```

It creates each repo privately (from a template, if the course names one), invites the
students with push access, lets the course's TAs team read them, and records each
repo's URL and permanent id — so even a renamed repo stays tracked. Run it again with a
longer roster and it merges the new rows in. It only ever touches this assignment's
repos.

**3. Sync.** Whenever something changes — you hand-edit a tsv, add a TA, change the
branch protection — `sync` makes GitHub match the record for the whole course: missing
repos, student access, the TAs team, and branch protection. Run it twice — the second
pass prints `nothing to do`:

```bash
gh-class-sak sync CS-101 --no-dryrun
```

The full sync contract — what each pass changes, what only ever happens on request, and
what sync never touches — is specified in the [commands reference](commands.md#sync).

Coming from GitHub Classroom? One command imports an org Classroom left behind — see
[Migrating from GitHub Classroom](migrating-from-github-classroom.md) for where
Classroom's bookkeeping lives now and the full walkthrough.

## Browse the course

With the course recorded, list what's there:

```console
$ gh-class-sak course list --org cs101-fall
scanning cs101-fall ...
COURSE      PREFIX  TAS  ASSIGNMENTS
cs101_fall  -       0    hw1(2) project(3)
```

The `repos` commands take the course and an assignment. With no config, as here, name
the org instead — it works whenever the org hosts a single course.

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
⚠️  dry run: no changes will be made. add --no-dryrun to apply
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
```

Add `--no-dryrun` and it actually clones, fast-forwarding any repo you already have.

## Where to next

- **[Commands](commands.md)** — the full reference: every command, every flag, and the
  classroom-meta repo in detail
- **[The Discord server](https://discord.gg/nyfCHTZJkt)** — questions, quick help, and
  other instructors running courses this way
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — the test suite stubs GitHub and Canvas, so
  you can hack on the tool without a course or a token
