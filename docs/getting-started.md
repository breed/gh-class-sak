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

## Try it first

Before pointing the tool at a real org, try any command on a made-up course — offline,
with nothing kept, so even `--apply` is safe:

```console
$ gh-class-sak demo course status cs101_fall
(demo: a made-up course, offline — nothing is kept)
COURSE    cs101_fall  (org cs101-fall)
ASSIGNMENT  REPOS  ACCEPTED  INVITED  NOT INVITED
hw1         0/2    0         0        0
project     0/3    0         0        0
TAS TEAM  cs101_fall-TAs (not created — run: gh-class-sak sync cs101_fall --org cs101-fall --apply)

to do:
  hw1: 2 rows without a recorded repo → gh-class-sak sync cs101_fall --org cs101-fall --apply
  project: 3 rows without a recorded repo → gh-class-sak sync cs101_fall --org cs101-fall --apply
  TAs team → gh-class-sak sync cs101_fall --org cs101-fall --apply
```

`gh-class-sak demo` alone describes the course and suggests more to try.

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

Rather than writing it by hand, let the tool write it — it asks for the org and the
Canvas details, then checks everything:

```bash
gh-class-sak help-me-setup --create-config
```

Run `gh-class-sak help-me-setup` any time after to verify the whole setup: the GitHub
token and its scopes, each configured org and its classroom-meta repo, and the Canvas
credentials. It also points at `gh-class-sak completion`, which turns on tab-completion
for your shell.

## Set up a course: three commands

Everything the tool knows lives in the org's private
[classroom-meta repo](commands.md#the-classroom-meta-repo) — a small versioned state repo
that every other command reads. Each course is a directory in it; each assignment is a
`.tsv` file in that directory, one row per team. Mutating commands are safe by
default — they *preview* with a ⚠️ until you add `--apply`.

**1. Record the course.** `course init` creates the classroom-meta repo when the org
doesn't have one yet, and records the course in it. The org is the single configured
`[ORGS]` entry — with several orgs configured, or none, pass `--org` (partial names
work). A new org is added to your config's `[ORGS]`, so no later command needs `--org`:

```console
$ gh-class-sak course init CS-101 --org cs101-fall
⚠️  dry run: no changes will be made. add --apply to make them
no canvas config; seed the [TAS] section by hand
⚠️  would record cs_101: prefix=CS-101 tas=-
⚠️  would create team "cs_101-TAs" in cs101-fall
⚠️  would add cs101-fall to the config's [ORGS]
⚠️  that was a preview: nothing changed. add --apply to make these changes
```

**2. Create an assignment's repos.** `assignment create` takes the course, the
assignment's name, and its roster — straight from Canvas with `--from-canvas`, or a
file you wrote with `--roster`. The simplest file is one person per line, for one
repo each:

```
jane@sjsu.edu
/msmith
```

For teams, write a table instead. Identities are `EMAIL/GITHUBID`, with either half
omissible (`jane@sjsu.edu/`, `/msmith`):

```
NAME       STUDENTS
team-1     jane@sjsu.edu/,/msmith
nightowls  /rpatel,/tk-codes
```

```bash
gh-class-sak assignment create CS-101 project --roster project.tsv --apply
```

It creates each repo privately (from a template, if the course names one), invites the
students with push access, lets the course's TAs team read them, and records each
repo's URL and permanent id — so even a renamed repo stays tracked. Run it again with a
longer roster and it merges the new rows in. It only ever touches this assignment's
repos.

**3. Sync.** Whenever something changes by hand — you edit a tsv, a student fixes their
Canvas profile link — `sync` makes GitHub match the record for the whole course:
missing repos, student access, the TAs team, and branch protection. It ends with a
one-line summary of what it changed. Run it twice — the second pass prints
`nothing to do`:

```bash
gh-class-sak sync CS-101 --apply
```

The full sync contract — what each pass changes, what only ever happens on request, and
what sync never touches — is specified in the [commands reference](commands.md#sync).

TAs and repo settings have their own commands, which record the change and apply it in
one step:

```bash
gh-class-sak course ta add CS-101 jane@sjsu.edu/ /msmith --apply
gh-class-sak course settings CS-101 --protection pr-review --apply
```

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

`gh-class-sak course status CS-101` shows what's left: repos not created yet,
invitations not accepted, and the command that fixes each.

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
`--apply`:

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  dry run: no changes will be made. add --apply to make them
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
⚠️  that was a preview: nothing changed. add --apply to make these changes
```

Add `--apply` and it actually clones, fast-forwarding any repo you already have. Add
`--before 2026-10-01` too, and each repo is left at what its last push before that
deadline (the end of that day) put on the branch, ready to grade — by GitHub's clock,
not the student's.

Starting next term's course? `course init CS-101-spring --like CS-101` copies the TAs,
templates, and repo settings over.

## Where to next

- **[Commands](commands.md)** — the full reference: every command, every flag, and the
  classroom-meta repo in detail
- **[The Discord server](https://discord.gg/nyfCHTZJkt)** — questions, quick help, and
  other instructors running courses this way
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — the test suite stubs GitHub and Canvas, so
  you can hack on the tool without a course or a token
