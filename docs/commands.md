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

## help-me-setup

Explain the config file and verify the whole setup: the GitHub token, the config's
`[ORGS]` (each org's reachability and classroom-meta repo, with its courses), and
the `[CANVAS]` credentials. With no config file it prints a template to start from.
Read-only; exits 0 when everything checks out, 1 when something needs attention.

```bash
gh-class-sak help-me-setup
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
gh-class-sak migrate-github-classroom ORG [--dryrun/--no-dryrun]
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
gh-class-sak canvas message-missing COURSE ASSIGNMENT [--dryrun/--no-dryrun]
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
gh-class-sak repos clone COURSE ASSIGNMENT [--dest DIR] [--dryrun/--no-dryrun]
```

It writes to disk, so it previews by default and only acts with `--no-dryrun`:

```console
$ gh-class-sak repos clone cs101-fall project --dest grading
⚠️  dry run: no changes will be made. add --no-dryrun to apply
⚠️  would clone cs101-fall/project-team-1 -> grading/team-1
⚠️  would clone cs101-fall/project-nightowls -> grading/nightowls
⚠️  would clone cs101-fall/project-team-3 -> grading/team-3
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
gh-class-sak course init COURSE [--org ORG] [--prefix PREFIX] [--template OWNER/NAME] [--canvas-course NAME] [--dryrun/--no-dryrun]
```

The argument is the **new course's name**, taken literally — partials only ever
resolve courses that already exist. The org comes from `--org` (matched partially
against `[ORGS]`), from the single configured org, or — with no config — from the
argument itself; with several orgs configured and no `--org`, it's an error.

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
⚠️  dry run: no changes will be made. add --no-dryrun to apply
no canvas config; seed the [TAS] section by hand
⚠️  would record cs_101: prefix=CS-101 tas=-
⚠️  would create team "cs_101-TAs" in cs101-fall
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
  `(matches tas)`, `(not created — run: gh-class-sak sync)`, or the members that are
  invited but not yet accepted, missing, or extra

Once repos are recorded, `repos list`, `repos members`, `repos missing`, and `repos clone`
all include them by id — so a renamed repo shows up under its original team name instead
of silently vanishing.

## course delete

Delete a course from the classroom-meta repo, after showing its recorded state and
confirming:

```
gh-class-sak course delete COURSE [--org ORG] [--delete-repo/--no-delete-repo] [--dryrun/--no-dryrun]
```

An **empty** course (no assignment tsvs) asks for a simple yes/no. One **with
assignments** lists them and asks you to type the **full name of one of them** — the
type-to-confirm bar rises with what's at stake. The assignments' GitHub repos survive
by default; `--delete-repo` deletes every recorded repo too. Like every mutating
command it previews with `would …` lines until `--no-dryrun` — the confirmation happens
either way. The course's `<course>-TAs` team is left alone.

## assignment create

Record an assignment and create its repos. The roster comes from a table you wrote —
just the two columns, emails and logins mixed freely:

```
NAME       STUDENTS
team-1     jane@sjsu.edu/,/msmith
nightowls  /rpatel,/tk-codes
```

```
gh-class-sak assignment create COURSE NAME --roster FILE [--org ORG] [--template REPO_URL] [--remove-unlisted-contributors] [--dryrun/--no-dryrun]
```

The table lands in the course directory as `NAME.tsv`. Emails are resolved to GitHub
logins via the student's Canvas profile link — never a GitHub search; an email nothing
can resolve is a loud error. Under `--no-dryrun` it creates each missing repo
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
gh-class-sak sync (COURSE | --org ORG) [--remove-unlisted-contributors] [--dryrun/--no-dryrun]
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

What a run **writes back**: `REPO` and `REPO_ID` on the rows it realized — only the
tsvs that changed are rewritten, so hand-written `#` comments in untouched files
survive — committed and pushed as author `gh-class-sak`. What a run **never does**:
touch an org admin, modify the contents of an existing repo, remove branch
protection, delete a tsv, or delete a repo (beyond rolling back a shell it created
moments earlier in the seed-failure case above).

Sync is idempotent — run it twice and the second pass prints `nothing to do` — and,
like every mutating command, a preview with ⚠️ until `--no-dryrun`. Exit status: `1`
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
`assignment create` and `sync` put the effective settings on each repo's default
branch. GitHub can't protect a branch that doesn't exist yet, so a repo created without
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
