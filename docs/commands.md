# Commands

The full reference for every `gh-class-sak` command. Every `console` example on this
page is replayed byte-for-byte against the invented demo course by the test suite
(`tests/test_readme.py`), so the output shown is the output you get.

New here? Start with [Getting started](getting-started.md).

## The classroom argument

Every command's `CLASSROOM` argument names either a **GitHub org** or a **classroom**.
An org name (or a partial matching exactly one `[ORGS]` entry) wins first, without
touching any meta repo. Otherwise the configured orgs' classroom-meta repos are
searched for a classroom directory matching the name — so Canvas course names work.
Ambiguity is an error listing the candidates; with no config the argument is used
verbatim as an org name.

## help-me-setup

Explain the config file and verify the whole setup: the GitHub token, the config's
`[ORGS]` (each org's reachability and classroom-meta repo, with its classrooms), and
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
of a classroom's repos (Classroom set TAs up exactly like that) is left out of the
`STUDENTS` columns and recorded in the classroom's `tas` file instead — where the next
`meta apply` gives it team read and revokes the leftover per-repo write. Re-running the
migration also repairs rows imported before this detection existed.

The course repo prefix is derived from your answers: when every assignment's name is a
`-`-suffix of the repo-name prefix it was inferred from (repos `cmpe30-hw1-*`, assignment
`hw1`), the shared head (`cmpe30`) is recorded as the classroom's `prefix` — so
`prefix-assignment` keeps spelling the real repo names and future repos follow the same
naming.

```
gh-class-sak migrate-github-classroom ORG [--dryrun/--no-dryrun]
```

When the org isn't in the config's `[ORGS]` yet, it is added (the config file is created
if needed). Like every mutating command it previews by default — the questions are asked
first, then the plan prints as `would …` lines. Re-importing **never clobbers** a
recorded repo; rows merge like `meta assign`, so running it again after Classroom's
sunset picked up stragglers only adds what's new.

The [migration guide](migrating-from-github-classroom.md) walks through the whole move,
including what to do after the import.

## classrooms

List each classroom in an org and its assignments, straight from the org's
[classroom-meta repo](#the-classroom-meta-repo) — one line per assignment tsv. Pass the
org (or a course name) as the argument; with no argument, every org listed in the
`[ORGS]` section of the config is scanned. Orgs are never discovered from
your token — your account may belong to orgs with thousands of unrelated repos, and
scanning them would take forever.

```console
$ gh-class-sak classrooms cs101-fall
scanning cs101-fall ...
cs101_fall: hw1
cs101_fall: project
```

An org without a classroom-meta repo is an error pointing at `meta init`.

## repos list

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

## repos members

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

## repos missing

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

## repos clone

Clone every repo for an assignment into `--dest`, one directory per team, fast-forwarding
any that are already there.

```
gh-class-sak repos clone CLASSROOM ASSIGNMENT [--dest DIR] [--dryrun/--no-dryrun]
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
versioned, hand-editable, and invisible to students. Every command starts from it: an org
without one gets an error pointing at `meta init`. An org hosts a set of classrooms (two
Canvas sections often share one org). A classroom is a directory with a `classroom.ini`,
and **every `.tsv` file in it is an assignment**, named by its basename:

```
classroom-meta/
  sp26_cmpe_195a/                  one directory per classroom
    classroom.ini                  [CLASSROOM] optional prefix, template, repo settings
    tas                            one EMAIL/GITHUBID identity per line
    hw1.tsv                        one file per assignment: NAME  STUDENTS  REPO  REPO_ID
    project.tsv
```

The tsv files are the heart of it. You supply the first two columns — `NAME` (the team
suffix) and `STUDENTS`: comma-joined **identities** in `EMAIL/GITHUBID` syntax —
`joe@example.com/JoeDevExample` when both are known, `joe@example.com/` for email only
(resolved to a GitHub id via Canvas and then the GitHub search API), `/JoeDevExample`
for a bare GitHub id. A
repo's default name joins the non-empty parts of classroom `prefix`, assignment, and
`NAME` with dashes: with `prefix = sp26-195a`, row `team-1` of `hw1.tsv` becomes
`sp26-195a-hw1-team-1`; with no prefix, just `hw1-team-1`. The tool fills in the last two
columns when it creates the repo: the URL, and GitHub's **permanent numeric repo id** —
which is how a repo stays tracked even after students rename it.

### meta init

Create the classroom-meta repo (when the org doesn't have one yet) and record a
classroom. The argument is the **new course's name**, taken literally — partials only
ever resolve classrooms that already exist. The org comes from `--org` (matched
partially against `[ORGS]`), from the single configured org, or — with no config — from
the argument itself; with several orgs configured and no `--org`, it's an error.

With a Canvas config, the `tas` file is seeded from the course's TA and
teacher enrollments. `--prefix` defaults to the classroom argument itself (made
repo-name safe), so a new classroom's repos are namespaced by its course name; pass
`--prefix ""` to record none. Existing classrooms keep their recorded prefix — a
re-init never backfills one. `--canvas-course NAME` records the Canvas
course's name in `classroom.ini`, and the Canvas lookups use it from then on (otherwise
they match on the classroom directory name). The classroom's `<classroom>-TAs` team is
created right away, with the TAs as members and read access to whatever repos the
classroom already has — usually none yet. Like every mutating command, it previews by
default; in an org with no classroom-meta repo yet, a
`would create private ORG/classroom-meta` line comes first:

```console
$ gh-class-sak meta init CS-101 --org cs101-fall
⚠️  dry run: no changes will be made. add --no-dryrun to apply
no canvas config; seed the tas file by hand
⚠️  would record cs_101: prefix=CS-101 tas=-
⚠️  would create team "cs_101-TAs" in cs101-fall
```

### meta assign

Feed it a team table — just the two columns, emails and logins mixed freely:

```
NAME       STUDENTS
team-1     jane@sjsu.edu/,/msmith
nightowls  /rpatel,/tk-codes
```

```
gh-class-sak meta assign CLASSROOM project.tsv [--assignment NAME] [--dryrun/--no-dryrun]
```

The table lands in the classroom directory as an assignment named after the file's
basename (`project.tsv` → `project`); `--assignment` overrides that. Emails are resolved
to GitHub logins via the student's Canvas profile link, then the GitHub search API; an
email nothing can resolve is a loud error. Under `--no-dryrun` it creates each missing
repo (privately, from the template when `classroom.ini` names one), records the URL and
repo id, and grants the listed students push. Re-importing an updated table changes
student lists but **never clobbers a recorded repo**.

Instead of a file, `--from-canvas` builds the table from the Canvas roster
(`--assignment` is required then, since there's no filename to name it):

```
gh-class-sak meta assign CLASSROOM --from-canvas --assignment hw1 [--canvas-group SET]
```

Without `--canvas-group`, everyone enrolled in the course — students, instructors, and
TAs alike — gets a row: the `NAME` is the person's name made GitHub-safe (accents
stripped, anything a repo name can't hold becomes `-`), and the `STUDENTS` entry is
their `email/githubid` identity — both halves, as far as Canvas knows them. With `--canvas-group SET`, each **group** in that Canvas group set gets a
row instead, its members drawn from the roster the same way — and the group set's name
is recorded in `classroom.ini` under `[GROUP_SETS]` for the assignment. Everything else
works exactly like a file import: merge, never-clobber, dryrun first.

### meta apply

Reconcile the org to match the classroom-meta repo:

```
gh-class-sak meta apply CLASSROOM [--dryrun/--no-dryrun]
```

Naming a classroom reconciles just that one; naming the org reconciles every classroom
directory. For each one:

- rows without a repo yet — including ones you hand-added to any assignment's tsv — get
  created
- each classroom has its own **`<classroom>-TAs` team** (e.g. `sp26_cmpe_195a-TAs`) whose
  membership matches its `tas` file, added as a **read** collaborator on that classroom's
  student repos across all of its assignments — so TAs accept one org invite ever, and
  TAs of one classroom never gain access to another classroom's repos
- every listed student has **write** on their repo; non-admin collaborators who aren't
  listed are revoked — org admins are never touched
- every recorded repo's default branch carries the classroom's protection settings
- run it twice: the second pass prints `nothing to do`

### Repo settings

`classroom.ini` can also carry branch-protection settings for the classroom's repos:

```
[CLASSROOM]
prefix = sp26-195a
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

### meta delete

Delete a classroom from the classroom-meta repo, after showing its recorded state and
confirming:

```
gh-class-sak meta delete CLASSROOM [--delete-repo/--no-delete-repo] [--dryrun/--no-dryrun]
```

An **empty** classroom (no assignment tsvs) asks for a simple yes/no. One **with
assignments** lists them and asks you to type the **full name of one of them** — the
type-to-confirm bar rises with what's at stake. The assignments' GitHub repos survive
by default; `--delete-repo` deletes every recorded repo too. Like every mutating
command it previews with `would …` lines until `--no-dryrun` — the confirmation happens
either way. The classroom's `<classroom>-TAs` team is left alone.

### meta show

Print a classroom's recorded state — prefix, template, TAs, effective repo settings, and
one table per assignment — checked against the live org:

- each student in the tables carries a membership marker for their repo: ✅ means
  collaborator, 📧 means invited but not yet accepted, ❌ means not a collaborator at
  all (rows whose repo isn't created yet stay unmarked; a legend prints whenever
  markers appear)
- a `TAS TEAM` line compares the classroom's `<classroom>-TAs` team to the `tas` file:
  `(matches tas)`, `(not created — run: meta apply)`, or the members that are invited
  but not yet accepted, missing, or extra

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

- **Renamed repos are invisible unless recorded.** An assignment's unrecorded repos are
  found by name prefix, so if a team renames `project-widgets` to `widgets` it drops out
  of listings — until the repo is recorded in its assignment's tsv (`REPO_ID`), which
  tracks it by permanent id and survives any rename.
- Students are matched to Canvas by fuzzy name comparison, not by ID. A student whose
  GitHub profile has no real name can't be matched.
