# The classroom-meta files

Everything gh-class-sak knows about a course lives in a private repo named
`classroom-meta` inside the org — plain text, versioned, hand-editable, invisible to
students. This page documents the files: where they live, their formats, and how the
`[TAS]` section becomes a real GitHub team.

Hand edits are first-class: clone the repo, edit, commit, push — the next command
picks the changes up. The tool itself commits with author `gh-class-sak`.

## Layout

```
classroom-meta/
  cs101_fall/                      one directory per classroom
    classroom.ini                  everything but the rosters (sections below)
    hw1.tsv                        one file per assignment, named by its stem
    project.tsv
  cs210_spring/                    an org hosts as many classrooms as you need
    classroom.ini
    lab1.tsv
```

A **classroom** is any directory containing a `classroom.ini`; its name is the
normalized Canvas course partial (lowercase; spaces and `-` become `_`). An
**assignment** is any `*.tsv` file in the directory, named by its basename. Deleting
an assignment is a hand `git rm` — the tool never deletes a tsv it didn't write.

## classroom.ini

A complete file — `cs210_spring`'s, say:

```ini
[CLASSROOM]
prefix = cs210
template = cs101-fall/starter
canvas_course = CS-210
protection = pr-review
linear_history = true
force_push = false

[TAS]
ta-alice@sjsu.edu/ta-alice
/prof-lee

[TEMPLATE]
lab1 = https://github.com/cs101-fall/lab1-starter.git

[GROUP_SETS]
lab1 = Lab Groups
```

Every key is optional; unset keys are simply not written back.

- **`[CLASSROOM]`** — `prefix`: the repo-name namespace; a repo's default name joins
  the non-empty parts of prefix, assignment, and row `NAME` with `-`
  (`cs210-lab1-team-1`). `template`: an `OWNER/NAME` GitHub template repo used
  when creating any of the classroom's repos. `canvas_course`: the Canvas course name,
  preferred over the directory name for Canvas lookups. `protection`
  (`none`/`pr-review`), `linear_history` (default true), `force_push` (default false):
  branch protection applied to each repo's default branch by `meta assign`/`meta apply`.
- **`[TAS]`** — one identity per line (see identities, below). Realized as the TA
  team.
- **`[TEMPLATE]`** — one `ASSIGNMENT = REPO_URL` record each: new repos for that
  assignment are seeded from a shallow clone of the URL, pushed as a single fresh
  commit (content, not history). Takes precedence over the classroom-wide `template`.
  Recorded by `meta assign --template`.
- **`[GROUP_SETS]`** — one `ASSIGNMENT = SET` record each: which Canvas group set an
  assignment's teams came from. Recorded by `meta assign --from-canvas --canvas-group`.

A classroom recorded before the `[TAS]` section existed may still carry a standalone
`tas` file; it is read as a fallback, and the next save migrates its entries into the
ini and removes it.

## The assignment tsv

```
NAME       STUDENTS                     REPO                                          REPO_ID
team-1     jane@sjsu.edu/jdoe,/msmith   https://github.com/cs101-fall/project-team-1  1042
nightowls  /rpatel,/tk-codes            -                                             -
```

Columns split on any whitespace run (no column may contain spaces), `-` means empty,
`#` starts a comment, and a `NAME STUDENTS…` header row is ignored — so hand-edited
files parse fine.

- **`NAME`** — the team: the suffix appended to `prefix-assignment` to name the repo.
- **`STUDENTS`** — comma-joined **identities** who get write access. An identity is
  `EMAIL/GITHUBID`: both halves (`jane@sjsu.edu/jdoe`), email only (`jane@sjsu.edu/`,
  resolved via the Canvas profile's GitHub link), or GitHub id only (`/msmith`, used
  directly).
- **`REPO`, `REPO_ID`** — filled in by the tool when it creates the repo: the URL, and
  GitHub's permanent numeric id. The id is how a repo stays tracked after students
  rename it — and it is **never clobbered** by a re-import; you only ever supply the
  first two columns.

`meta show` renders the recorded state checked against the live org:

```console
$ gh-class-sak meta show cs101-fall
CLASSROOM cs101_fall
PREFIX    -
TAS       -
TAS TEAM  cs101_fall-TAs (not created — run: meta apply)
SETTINGS  protection=none linear_history=true force_push=false

ASSIGNMENT hw1
NAME    STUDENTS  REPO  REPO_ID
jdoe    /jdoe     -     -
rpatel  /rpatel   -     -

ASSIGNMENT project
NAME       STUDENTS           REPO  REPO_ID
team-1     /jdoe,/msmith      -     -
nightowls  /rpatel,/tk-codes  -     -
team-3     /lchen             -     -
```

## TA teams

Each classroom's `[TAS]` section is realized as an org team named
**`<classroom>-TAs`** (GitHub slugs that to lowercase; the tool looks teams up by
slug, so hand-created `-tas` teams match too):

- **Created by `meta init`**, with the resolved TA identities as members — so the team
  exists from day one, before any repos do. TAs accept **one org invitation ever**,
  instead of one per repo.
- **Reconciled by `meta apply`**: membership is made to match `[TAS]` exactly, and the
  team is granted **read** on every one of the classroom's repos — across all its
  assignments — while team grants outside the classroom are revoked (the
  classroom-meta repo itself excepted). TAs who somehow hold direct per-repo write
  (GitHub Classroom set them up that way) are demoted to the team's read access when
  `meta apply` runs with `--remove-unlisted-contributors`; without it their extra
  write is only warned about.
- **Pending invitations count as membership** — an invited TA who hasn't accepted yet
  is not re-invited, and `meta show` reports them as `invited, not yet accepted`
  rather than missing.
- Scoping is the point: TAs of one classroom never gain access to another classroom's
  repos, even in a shared org.

`meta show`'s `TAS TEAM` line is the health check: `(matches tas)`,
`(not created — run: meta apply)`, or the invited/missing/extra members.
