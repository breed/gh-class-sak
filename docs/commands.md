# Commands

The full reference for every `gh-class-sak` command. Every `console` example on this
page is replayed byte-for-byte against the invented demo course by the test suite
(`tests/test_readme.py`), so the output shown is the output you get.

New here? Start with [Getting started](getting-started.md).

## The words, and the COURSE argument

A **course** is one Canvas course, hosted in a GitHub org (an org can host several). An
**assignment** is one repo per student or group in a course — assignment `hw1` gives
repos like `hw1-jdoe`. A **team** is the student or group behind one repo.

A `COURSE` argument names a course recorded in an org's
[classroom-meta repo](#the-classroom-meta-repo). It is looked up in `--org`, or else in
every org in the config's `[ORGS]` — partial names work, so Canvas course names do too;
an exact name beats a partial one, and an ambiguity is an error listing the candidates.
With no config, pass `--org`. An org name is never taken for a course: `course`,
`assignment`, and `sync` say to pass it as `--org` instead.

The `repos` and `canvas` commands are more lenient: their `COURSE` may also name the
org, when it hosts a single course — with no config, the argument is used verbatim as
the org name.

## Previews, summaries, and next steps

Every command that changes something previews by default: it opens with
`⚠️  dry run: no changes will be made`, prints a `⚠️  would …` line per change, and —
when it previewed anything — ends with
`⚠️  that was a preview: nothing changed. add --apply to make these changes`, since a long
preview scrolls the opening line away. `--apply` makes the changes (`--no-dryrun`
is the same flag, and still works).

`sync`, `assignment create`, `course ta`, and `course settings` end with a one-line
summary of what changed (or, in a preview, what would) and how many warnings and errors
were printed along the way — `summary: 2 repos created, 2 invitations, 1 warning`.
After a real run, `course init` and `assignment create` name the next step.

## help-me-setup

Explain the config file and verify the whole setup: the GitHub token (including
whether a classic token has the `repo` scope that private repos need — with the
`gh auth refresh` command that adds it), the config's `[ORGS]` (each org's reachability
and classroom-meta repo, with its courses), and the `[CANVAS]` credentials. With no
config file it prints a template to start from. Exits 0 when everything checks out, 1
when something needs attention.

```
gh-class-sak help-me-setup [--create-config]
```

`--create-config` writes the config for you: it asks for the GitHub org and,
optionally, the Canvas URL and API token (typed hidden), then runs the checks against
the new file. It only ever adds the sections the config is missing — nothing already
there changes — and a file holding a Canvas token is made readable by you alone. At a
terminal, a missing config file prompts the same offer. Otherwise the command is
read-only.

## demo

Try any command on a made-up course, offline:

```
gh-class-sak demo [COMMAND...]
```

The course is the invented one every example in these docs is built on — org
`cs101-fall`, course `cs101_fall`, assignments `hw1` and `project`. Nothing touches
GitHub or Canvas, and nothing is kept: each run starts from the same course in a
temporary directory that is deleted afterwards, so `--apply` is safe (even
`repos clone --apply` clones real, local git repos). Without a command it describes
the course and suggests a few. Canvas features need a real Canvas, so they aren't in
the demo.

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

## migrate-github-classroom

Import an org left behind by GitHub Classroom. Classroom named repos
`ASSIGNMENT-TEAM` but kept no record of which course an assignment belonged to — orgs
often hosted several — so this is interactive: it scans the org's repos, infers the
assignments from shared name prefixes (the most specific prefix wins, and one-off repos
are ignored and listed), then asks, per assignment, **which course it belongs to**
(blank skips it) and **what to call it** (default: the inferred prefix). Each imported
row carries the team name, the repo's collaborators as the students, and the repo's url
and **permanent id** — so every imported repo is rename-proof from day one.

Staff are detected, not imported as students: a login with write access on **every** one
of a course's repos (Classroom set TAs up exactly like that) is left out of the
`STUDENTS` columns and recorded in classroom.ini's `[TAS]` section instead — where the next
`sync` gives it team read and revokes the leftover per-repo write. When *everyone*
is on every repo (one group owning all the repos), there is no staff signal: the
migration warns and records everyone as students. Re-running the
migration also repairs rows imported before this detection existed.

The course repo prefix is derived from your answers: when every assignment's name is a
`-`-suffix of the repo-name prefix it was inferred from (repos `cs210-hw1-*`, assignment
`hw1`), the shared head (`cs210`) is recorded as the course's `prefix` — so
`prefix-assignment` keeps spelling the real repo names and future repos follow the same
naming.

```
gh-class-sak migrate-github-classroom ORG [--apply]
```

When the org isn't in the config's `[ORGS]` yet, it is added (the config file is created
if needed). Like every mutating command it previews by default — the questions are asked
first, then the plan prints as `would …` lines. Re-importing **never clobbers** a
recorded repo; rows merge like `assignment create`, so running it again after Classroom's
sunset picked up stragglers only adds what's new.

The [migration guide](migrating-from-github-classroom.md) walks through the whole move,
including what to do after the import.

## repos list

List the repos for an assignment. Both arguments accept partial names.

```
gh-class-sak repos list COURSE ASSIGNMENT [OPTIONS]
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

## repos members

Every commit author per repo, mined from commit history. Addresses ending in
`@users.noreply.github.com` are skipped, and commits from someone with no linked GitHub
account show `?`.

```console
$ gh-class-sak repos members cs101-fall project
TEAM       GITHUB_ID  NAME        EMAIL
team-1     jdoe       Jane Doe    jane.doe@cs101.edu
nightowls  rpatel     Riya Patel  riya@cs101.edu
```

This is the fastest way to find the email a student actually commits with, which is often
not the one on their Canvas profile.

## repos missing

Canvas students, or Canvas groups, with no repo for the assignment. Both modes need the
Canvas config.

```
gh-class-sak repos missing COURSE ASSIGNMENT [--group CATEGORY]
```

Without `--group`, a student counts as missing when their GitHub id — taken from the
GitHub link on their Canvas profile — is not a collaborator on any repo, and their name
doesn't fuzzy-match any collaborator's profile name.

With `--group`, it lists Canvas groups that no repo could be matched to, along with their
members.

## canvas message-missing

Where `repos missing` tells *you* who is stranded, this tells *them*. It checks every
enrolled student against an assignment's repos and sends a Canvas message to each one
stuck on the way to their repo — one of three texts, each saying exactly what to do:

```
gh-class-sak canvas message-missing COURSE ASSIGNMENT [--apply]
```

- **no-link** — the Canvas profile has no GitHub link: asks them to add
  `https://github.com/YOUR-USERNAME` under Account → Profile → Links.
- **bad-link** — the profile links to a GitHub account that doesn't exist (a typo, or
  a renamed/deleted account), or to one of GitHub's own pages — the classic being
  `github.com/dashboard`, pasted straight from the address bar while signed in: asks
  them to fix the link.
- **invited** — their account holds an unaccepted invitation to their assignment repo:
  asks them to accept it (naming the repo URL), and warns that GitHub invitations
  expire after 7 days.

Students already collaborating on a repo are left alone, and Canvas's Student View
"Test Student" is ignored — it isn't a person, and Canvas refuses to message it. A student with a working
GitHub account but neither repo access nor a pending invitation gets no message — that
one isn't theirs to fix — and is instead a loud, red error aimed at you (the run exits
1): the org is out of sync with the meta, and `sync` is the cure. Needs the
Canvas config. Like every mutating
command it previews by default: the dry run lists who would get which message and
prints the full message texts, so nothing goes out sight-unseen. The texts live in one
place at the top of `gh_class_sak/commands/canvas.py` if you want to reword them.

## repos clone

Clone every repo for an assignment into `--dest`, one directory per team, fast-forwarding
any that are already there.

```
gh-class-sak repos clone COURSE ASSIGNMENT [--dest DIR] [--before DEADLINE] [--apply]
```

It writes to disk, so it previews by default and only acts with `--apply`.
`--before DEADLINE` leaves each repo — detached, ready to grade — at the commit its
default branch held after its **last push** at or before the deadline, and adds an `AT`
column with that commit's short sha and push time. A bare date means the end of that
day (`--before 2026-10-01`), or give a time (`--before "2026-10-01 17:00"`), both local
time.

The push times come from GitHub's own record of the branch (the repo's Activity view),
not from commit dates, which students' machines set. So a wrong clock, a faked commit
date, or a force push after the deadline can't change which commit is graded. A commit
that a later force push took off the branch is fetched by its id. A repo with no push
before the deadline is a loud error and stays at its latest commit. A repo GitHub has
no push record for at all — or that GitHub definitively won't share one for — falls
back to commit dates, with a warning saying so, and its `AT` cell reads `committed`
instead of `pushed`. A push record GitHub can't serve right now (a server error, a rate
limit, bad credentials) is that repo's error, with a retry hint; it never falls back,
since that would quietly grade by commit dates because of a passing outage. The next clone returns a detached
checkout to its branch before pulling (a checkout whose local edits block that is left
alone and reported as `cannot-reattach`).

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  dry run: no changes will be made. add --apply to make them
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
⚠️  that was a preview: nothing changed. add --apply to make these changes
```

Your token is handed to git through the environment, so it never appears in `ps` output,
in the clone URL, or in the checked-out `.git/config`.

## The classroom-meta repo

All course state lives in a private repo named `classroom-meta` inside the org —
versioned, hand-editable, and invisible to students; the complete file-format reference
is [The classroom-meta files](classroom-meta-files.md). Every command starts from it: an
org without one gets an error pointing at `course init` — one that also names the token as
a suspect, because a private repo the token can't see 404s exactly like one that was
never created. Note that TAs are not given access to it: the `<course>-TAs` team is
granted read on the student repos only, so a TA who will run these commands needs the
team (or their account) added to `classroom-meta` by hand. An org hosts a set of courses (two
Canvas sections often share one org). A course is a directory with a `classroom.ini`
(the file keeps its name from the tool's GitHub Classroom days),
and **every `.tsv` file in it is an assignment**, named by its basename:

```
classroom-meta/
  cs101_fall/                      one directory per course
    classroom.ini                  [CLASSROOM] prefix and settings; [TAS] one
                                   identity per line; [TEMPLATE] and [GROUP_SETS]
                                   one ASSIGNMENT = VALUE each
    hw1.tsv                        one file per assignment: NAME  STUDENTS  REPO  REPO_ID
    project.tsv
```

The tsv files are the heart of it. You supply the first two columns — `NAME` (the team
suffix) and `STUDENTS`: comma-joined **identities** in `EMAIL/GITHUBID` syntax —
`joe@example.com/JoeDevExample` when both are known, `joe@example.com/` for email only
(resolved to a GitHub id via the Canvas profile's GitHub link), `/JoeDevExample`
for a bare GitHub id. A
repo's default name joins the non-empty parts of the course's `prefix`, assignment, and
`NAME` with dashes: with `prefix = sp26-195a`, row `team-1` of `hw1.tsv` becomes
`sp26-195a-hw1-team-1`; with no prefix, just `hw1-team-1`. A default name longer than
GitHub's 100-character limit is cut off at 100. When another row — in any course in
the org — already holds that name, the row gets the first free numbered name instead
(`…-2`, `…-3`, its `NAME` part cut shorter to make room), and the run says so; two rows
never share a repo. A prefix and assignment that leave no room at all for team names
are an error. The tool fills in the last two columns when it creates the repo: the URL,
and GitHub's **permanent numeric repo id** —
which is how a repo stays tracked even after students rename it.

## course init

Create the classroom-meta repo (when the org doesn't have one yet) and record a
course:

```
gh-class-sak course init COURSE [--org ORG] [--prefix PREFIX] [--template OWNER/NAME] [--canvas-course NAME] [--apply]
```

The argument is the **new course's name**, taken literally — partials only ever
resolve courses that already exist. The org comes from `--org` (matched partially
against `[ORGS]`), from the single configured org, or — with no config — from the
argument itself; with several orgs configured and no `--org`, it's an error. An org
that isn't in the config's `[ORGS]` yet is added (the file is created if needed), so
every later command finds the course without `--org`.

With a Canvas config, the `[TAS]` section is seeded from the course's TA and
teacher enrollments. `--prefix` defaults to the course argument itself (made
repo-name safe), so a new course's repos are namespaced by its name; pass
`--prefix ""` to record none. Existing courses keep their recorded prefix — a
re-init never backfills one. `--template` records an `OWNER/NAME` GitHub template repo
for every repo the course creates. `--canvas-course NAME` records the Canvas
course's name in `classroom.ini`, and the Canvas lookups use it from then on (otherwise
they match on the course directory name). The course's `<course>-TAs` team is
created right away, with the TAs as members and read access to whatever repos the
course already has — usually none yet. Like every mutating command, it previews by
default; in an org with no classroom-meta repo yet, a
`would create private ORG/classroom-meta` line comes first:

```console
$ gh-class-sak course init CS-101 --org cs101-fall
⚠️  dry run: no changes will be made. add --apply to make them
no canvas config; seed the [TAS] section by hand
⚠️  would record cs_101: prefix=CS-101 tas=-
⚠️  would create team "cs_101-TAs" in cs101-fall
⚠️  would add cs101-fall to the config's [ORGS]
⚠️  that was a preview: nothing changed. add --apply to make these changes
```

## course list

List the courses the classroom-meta repos record — one row per course with its prefix,
TA count, and each assignment with its team count. It reads only the meta repo, so it's
fast: no live-org checks (that's `course show`'s job). Without arguments it walks every
org in `[ORGS]`; `--org` lists one org, and a `COURSE` argument just that course:

```console
$ gh-class-sak course list --org cs101-fall
scanning cs101-fall ...
COURSE      PREFIX  TAS  ASSIGNMENTS
cs101_fall  -       0    hw1(2) project(3)
```

Orgs are never discovered from your token — your account may belong to orgs with
thousands of unrelated repos, and scanning them would take forever.

## course status

What's done and what's left in a course, and the command that does each next step:

```
gh-class-sak course status COURSE [--org ORG]
```

Per assignment it counts the rows that have a repo, and the students who have
accepted their invitation, are still invited, or aren't invited yet. Then the TAs
team, and a to-do list — each gap with the command that closes it (`sync`, or
`canvas message-missing` to chase invitations when Canvas is configured) — or
`all set` when there's nothing left. Read-only.

## course audit

Check who has access to a course's repos against who should:

```
gh-class-sak course audit COURSE [--org ORG]
```

It flags, each with the command or edit that fixes it:

- someone who has access to a repo, or an invitation to it, whom no row lists
- one GitHub account on rows for different people
- with a `[CANVAS]` config: an account that shares no part of the enrolled person's
  Canvas name — no word of it in the GitHub profile name, and no 3+-letter word of it in
  the login — the telltale of a wrong account; and a recorded GitHub id the person's
  Canvas profile no longer links. Rows cover everyone Canvas enrolls — students,
  instructors, and TAs — so all of them are checked. GitHub names are free-form, so a
  first name, nickname, or handle that shares anything with the person's name passes;
  names in any script count. What's left is worth a look, not necessarily wrong

A row whose identities don't all resolve is skipped for the first check, since a partial
list would misjudge who belongs. Without Canvas, the last two checks are skipped and the
output says so. Read-only; exits `1` when it finds a problem, `0` otherwise. A real
`sync` runs it at the end for every course it synced. What the tool itself changed, and
why, is in the course's [`audit.log`](classroom-meta-files.md#auditlog).

## course show

Print a course's recorded state — prefix, template, TAs, effective repo settings, and
one table per assignment — checked against the live org:

```
gh-class-sak course show COURSE [--org ORG]
```

- each student in the tables carries a membership marker for their repo: ✅ means
  collaborator, 📧 means invited but not yet accepted, ❌ means not a collaborator at
  all (rows whose repo isn't created yet stay unmarked; a legend prints whenever
  markers appear)
- a `TAS TEAM` line compares the course's `<course>-TAs` team to the `[TAS]` section:
  `(matches tas)`, `(not created — run: gh-class-sak sync COURSE --org ORG --apply)`, or the members that are
  invited but not yet accepted, missing, or extra

Once repos are recorded, `repos list`, `repos members`, `repos missing`, and `repos clone`
all include them by id — so a renamed repo shows up under its original team name instead
of silently vanishing.

With `--like OTHER` a new course starts from an existing one — last term's, say: its
TAs, template, per-assignment starter templates, and repo settings are copied. Never
its prefix (the repo names would collide) or its assignments; only a new course can be
seeded that way, and flags you pass beat the copy.

## course delete

Delete a course from the classroom-meta repo, after showing its recorded state and
confirming:

```
gh-class-sak course delete COURSE [--org ORG] [--delete-repo/--no-delete-repo] [--apply]
```

An **empty** course (no assignment tsvs) asks for a simple yes/no. One **with
assignments** lists them and asks you to type the **full name of one of them** — the
type-to-confirm bar rises with what's at stake. The assignments' GitHub repos survive
by default; `--delete-repo` deletes every recorded repo too. Like every mutating
command it previews with `would …` lines until `--apply` — the confirmation happens
either way. The course's `<course>-TAs` team is left alone.

## course ta

Add or remove a course's TAs — the `[TAS]` record and the `<course>-TAs` team change
together, so there's no `classroom.ini` to edit by hand:

```
gh-class-sak course ta add COURSE IDENTITY... [--org ORG] [--apply]
gh-class-sak course ta remove COURSE IDENTITY... [--org ORG] [--apply]
```

An `IDENTITY` is `EMAIL/GITHUBID`, `EMAIL/` (resolved via the Canvas profile's GitHub
link), or `/GITHUBID`. `add` records the new TAs and invites them to the team, which
already reads every one of the course's repos; adding a current TA only warns. `remove`
takes either half of an identity, drops the matching TAs from the record, and removes
them from the team; naming someone who isn't a TA is an error and changes nothing.

## course settings

Show a course's repo settings, or change them:

```
gh-class-sak course settings COURSE [--org ORG] [--protection none|pr-review] [--linear-history/--no-linear-history] [--force-push/--no-force-push] [--template OWNER/NAME] [--apply]
```

With no options it prints the effective settings. A change is recorded in
`classroom.ini`, and a protection change is put on the default branch of every recorded
repo in the same run (empty repos get their welcome commit first) — the mechanics and
caveats are under [Repo settings](#repo-settings). A `--template` only affects repos
created from then on; `--template ""` removes it. Setting a value the course already
has is `nothing to do`.

## assignment create

Record an assignment and create its repos. A roster is required to create repos — it
says who gets one, and comes from one of:

| Roster | Repos |
|---|---|
| `--from-canvas` | one per enrolled person — students, instructors, and TAs |
| `--from-canvas --canvas-group SET` | one per group in a Canvas group set |
| `--roster FILE` | one per person or team listed in the file |

A team project from a Canvas group set, seeded from a starter repo:

```bash
gh-class-sak assignment create CS-101 project --from-canvas \
    --canvas-group "Project Groups" --template URL --apply
```

A `--roster` file can be a table you wrote — just the two columns, emails and logins
mixed freely:

```
NAME       STUDENTS
team-1     jane@sjsu.edu/,/msmith
nightowls  /rpatel,/tk-codes
```

```
gh-class-sak assignment create COURSE NAME --roster FILE [--org ORG] [--template REPO_URL] [--remove-unlisted-contributors] [--apply]
```

A roster can also be a plain list, one person per line — an email, a `/GITHUBID`, or
both as `EMAIL/GITHUBID` — for one repo per person, named by the GitHub id when known
or else the email's local part. A roster file that mixes the two formats or has a
malformed row is an error naming the line, with an example of each format.

The table lands in the course directory as `NAME.tsv`. Emails are resolved to GitHub
logins via the student's Canvas profile link — never a GitHub search; an email nothing
can resolve is a loud error. Under `--apply` it creates each missing repo
(privately, from the template when there is one), records the URL and repo id, and
grants the listed students push. It then brings **this assignment's** repos in line
exactly as [`sync`](#sync)'s passes 2–3 would — students missing from a recorded repo
are invited, unlisted collaborators are warned about (`--remove-unlisted-contributors`
revokes them, with the same safety rule for unresolved identities), empty repos are
welcome-seeded, drifted branch protection is re-applied — and gives the course's
`<course>-TAs` team read on them, so new repos are TA-readable immediately. The rest of
the course — other assignments' repos, the TA team's membership, a TA team that
doesn't exist yet — is left to `sync`. Running it again with an updated roster merges
the new rows in and changes student lists, but **never clobbers a recorded repo**.

`--template REPO_URL` gives the assignment starter content: the URL is validated first
(`git ls-remote`; an unreachable repo is an error before anything happens), recorded in
`classroom.ini`'s `[TEMPLATE]` section as `ASSIGNMENT = REPO_URL`, and every **new**
repo created for the assignment — now or by a later `sync` — is seeded from a
shallow clone of it, pushed as a single fresh commit so students get the content
without the template's history. A `[TEMPLATE]` record takes precedence over the
course-wide `template` for its assignment, and `--template` without a roster records
or updates a template alone.

Instead of a file, `--from-canvas` builds the roster from Canvas:

```
gh-class-sak assignment create COURSE NAME --from-canvas [--canvas-group SET] [--remove-dropped]
```

Without `--canvas-group`, everyone enrolled in the course — students, instructors, and
TAs alike — gets a row: the `NAME` is the person's name made GitHub-safe (accents
stripped, anything a repo name can't hold becomes `-`), and the `STUDENTS` entry is
their `email/githubid` identity — both halves, as far as Canvas knows them. With
`--canvas-group SET`, each **group** in that Canvas group set gets a row instead, its
members drawn from the roster the same way — and the group set's name is recorded in
`classroom.ini` under `[GROUP_SETS]` for the assignment. Everything else works exactly
like a file import: merge, never-clobber, dryrun first.

A recorded row whose person (or group) is no longer in Canvas — a student who dropped
the class — is warned about and left in place; `--remove-dropped` removes the row
instead. The row's repo is never deleted: it stays on GitHub, untracked, with its
collaborators intact (the run warns about each repo it leaves behind, and the next
`sync` revokes the TA team's read grant on it). A student who is still enrolled but
whose Canvas entry carries neither an email nor a GitHub link is never treated as
dropped.

## sync

Make GitHub match the classroom-meta repo:

```
gh-class-sak sync (COURSE | --org ORG) [--remove-unlisted-contributors] [--apply]
```

Naming a course syncs just that one; `--org` alone syncs every course in the org. The
files are the source of truth: a run works out what the org is missing and changes
only that, in four passes per course.

**1. Every row gets a repo.** A row whose `REPO_ID` is empty — imported or hand-added
to any assignment's tsv — is realized. If a repo already exists under the row's
default name (`prefix-assignment-NAME`), it is **adopted**: recorded, contents
untouched. Otherwise a private repo is created and seeded from the first of: the
assignment's `[TEMPLATE]` record (its content, as one fresh commit on the repo's
default branch), the course-wide `template` repo, or nothing (an empty repo). An
unreachable `[TEMPLATE]` url fails that row cleanly — the empty shell is deleted so
the next run retries, the rest of the course proceeds, and the run exits 1. The
row's listed students get **push** on the new repo.

**2. Students match the rows.** Every row with a recorded repo — found by its
permanent id, so a renamed repo still syncs — is checked. Listed students without
access are granted push; an unaccepted invitation counts as access, so nobody is
re-invited run after run. Collaborators and pending invitations the row does *not*
list are warned about and left in place — `--remove-unlisted-contributors` revokes
the collaborators and cancels the invitations instead. Org admins are never touched
either way. One safety rule overrides everything: if **any** identity in a row fails
to resolve (a removed Canvas link, a Canvas outage), that row's collaborators are
left entirely alone — a shrunken list must never masquerade as the roster — and the
run exits 1.

**3. Protection matches the settings.** Every recorded repo's default branch carries
the course's `protection`/`linear_history`/`force_push` — mechanics and caveats
under [Repo settings](#repo-settings).

**4. The TA team matches `[TAS]`.** Each course's **`<course>-TAs`** team is
created if missing, its membership is made exactly the `[TAS]` identities (pending
invitations count as membership; members not in `[TAS]` are removed), and it holds
**read** on exactly the course's repos — the per-assignment name matches plus
every recorded id — so TAs accept one org invite ever and never gain access to
another course's repos. Team grants outside the course are revoked, the
classroom-meta repo itself excepted.

What a run **writes back**: `REPO` and `REPO_ID` on the rows it realized, and the new
`REPO` url of a repo renamed on GitHub (it is found by its permanent id either way) — only the
tsvs that changed are rewritten, so hand-written `#` comments in untouched files
survive — plus a line in each course's
[`audit.log`](classroom-meta-files.md#auditlog) for every repo created or adopted and
every invitation, revoke, and TA team change, with the reason for it; all committed and
pushed as author `gh-class-sak`. A real run then ends with
[`course audit`](#course-audit)'s check of each course it synced, printing any problem
with its fix — it reports, and doesn't change sync's exit status. What a run **never does**:
touch an org admin, modify the contents of an existing repo, remove branch
protection, delete a tsv, or delete a repo (beyond rolling back a shell it created
moments earlier in the seed-failure case above).

Sync is idempotent — run it twice and the second pass prints `nothing to do` — and,
like every mutating command, a preview with ⚠️ until `--apply`. Exit status: `1`
when an identity didn't resolve or a template seed failed (the org may be part-way
synced; fix the cause and re-run), `2` when the course or its classroom-meta
repo can't be found at all.

### assignment create or sync?

`assignment create` is for something new to **record** — a roster table, a Canvas
roster, a template URL — and it only touches that assignment's repos. `sync` is for
changes that need to **land** across the course — a hand-edited tsv row, a new `[TAS]`
entry, changed repo settings, a student who fixed their Canvas profile link, a fresh
`migrate-github-classroom` import. Sync also takes a whole org in one run (`--org`
alone, and every course syncs).

### Repo settings

`classroom.ini` can also carry branch-protection settings for the course's repos:

```
[CLASSROOM]
prefix = sp26-195a
protection = pr-review     # none (default) or pr-review: require one approving review
linear_history = true      # default true: require a linear history
force_push = false         # default false: block force pushes
```

(The section keeps its `[CLASSROOM]` name from the tool's GitHub Classroom days.)
[`course settings`](#course-settings) changes them without editing the file.
`assignment create`, `sync`, and `course settings` put the effective settings on each
repo's default branch. GitHub can't protect a branch that doesn't exist yet, so a repo created without
a template gets a `WELCOME.md` initial commit first — the branch exists and the
protection lands in the same run. Both commands repair drift on every repo they cover,
checking first so an untouched org still syncs to `nothing to do`.

Two caveats: GitHub can't protect private repos on a free org plan — the tool warns and
moves on — and a protection write replaces the whole protection object, so hand-set extras
like required status checks don't survive it. The all-off trio (`protection = none`,
`linear_history = false`, `force_push = true`) asks for nothing and skips the protection
API entirely; existing protection is never removed.

## Renamed commands

Earlier versions named things after GitHub Classroom. The old commands still work —
unchanged, and hidden from `--help` — and at a terminal each one says what replaced it:

| Old | New |
|---|---|
| `meta init CLASSROOM` | `course init COURSE` |
| `meta list`, `classrooms` | `course list` |
| `meta show CLASSROOM` | `course show COURSE` |
| `meta delete CLASSROOM` | `course delete COURSE` |
| `meta assign CLASSROOM TABLE` | `assignment create COURSE NAME --roster TABLE` (it covers only that assignment; `sync` does the rest of the course) |
| `meta apply CLASSROOM` | `sync COURSE`, or `sync --org ORG` for every course in an org |

## completion

Print the tab-completion script for your shell, so commands, subcommands, and flags
complete on TAB:

```
gh-class-sak completion [bash|zsh|fish]
```

Without an argument it uses your login shell. Load it from your shell's startup file:

```bash
eval "$(gh-class-sak completion zsh)"       # in ~/.zshrc
eval "$(gh-class-sak completion bash)"      # in ~/.bashrc
gh-class-sak completion fish | source       # in ~/.config/fish/config.fish
```

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

- **Renamed repos are invisible unless recorded.** An assignment's unrecorded repos are
  found by name prefix, so if a team renames `project-widgets` to `widgets` it drops out
  of listings — until the repo is recorded in its assignment's tsv (`REPO_ID`), which
  tracks it by permanent id and survives any rename.
- Students are matched to Canvas by fuzzy name comparison, not by ID. A student whose
  GitHub profile has no real name can't be matched.
