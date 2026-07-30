# Migrating from GitHub Classroom

GitHub Classroom is gone, but everything it managed for you is still recoverable from
what it left behind: an org full of repos named `ASSIGNMENT-TEAM`. This guide explains
where each piece of Classroom's bookkeeping lives now, and walks through the
one-command import.

## Where Classroom's information lives now

Classroom kept its state in its own database, behind its own UI. gh-class-sak keeps the
same state in a **private git repo named `classroom-meta`** inside your org — versioned,
hand-editable, diffable, and invisible to students:

```
classroom-meta/
  cs_101/                          one directory per classroom
    classroom.ini                  [CLASSROOM] optional prefix, template, repo settings
    tas                            one EMAIL/GITHUBID identity per line
    hw1.tsv                        one file per assignment: NAME  STUDENTS  REPO  REPO_ID
    project.tsv
```

| GitHub Classroom managed… | …now lives in |
|---|---|
| a classroom, tied to an org | a directory in the org's `classroom-meta` repo, named for the course |
| an assignment and its accepted repos | one `<assignment>.tsv` per assignment |
| which student/team owns which repo | the tsv rows: `NAME  STUDENTS  REPO  REPO_ID` |
| repos surviving a rename | `REPO_ID` — GitHub's permanent numeric id, recorded per row |
| the roster | the `STUDENTS` columns (plus Canvas, via the config, for names and emails) |
| TA access everywhere | the `tas` file — realized as a `<classroom>-tas` team with read access |
| starter code | `classroom.ini`: `template = OWNER/NAME`, used when repos are created |
| repo protection | `classroom.ini`: `protection`, `linear_history`, `force_push` |

The commands are the interface to that state: `meta assign` imports team tables,
`meta apply` reconciles the org to match the files, and `classrooms` / `repos …` read
them for discovery. The full details are in the
[commands reference](commands.md#the-classroom-meta-repo).

## The import, in one command

Classroom's repo names carry the assignment but **not the course** — orgs often hosted
several courses — so the import is interactive: it infers the assignments from shared
name prefixes, then asks you, per assignment, which course it belongs to (blank skips
it) and what to call it. A session looks like this (illustrative — your names will
differ):

```
$ gh-class-sak migrate-github-classroom cs101-fall
hw1: 2 repos (jdoe, rpatel)
  course for "hw1" (blank to skip): CS-101
  assignment name for "hw1" [hw1]:
project: 3 repos (team-1, nightowls, team-3)
  course for "project" (blank to skip): CS-101
  assignment name for "project" [project]:
⚠️  would add cs101-fall to [ORGS] in /home/you/.config/gh-class-sak.ini
⚠️  would record cs_101 tas: /ta-alice
⚠️  would record cs_101/hw1: jdoe, rpatel
⚠️  would record cs_101/project: team-1, nightowls, team-3
⚠️  would create private cs101-fall/classroom-meta
⚠️  would record cs_101: 2 assignments, 5 teams
```

Everything above is a *preview* — like every mutating command it does nothing until you
re-run with `--no-dryrun`. What the import records:

- **every repo, tracked by permanent id** — Classroom's accepted-assignment list is
  reconstructed as tsv rows with `REPO` and `REPO_ID` filled in, so a team renaming
  their repo can't hide it
- **collaborators as the students** — each row's `STUDENTS` column is the repo's
  write-access collaborators, recorded as `/githubid` identities
- **TAs detected, not imported as students** — a login with write access on *every* one
  of a classroom's repos (exactly how Classroom set staff up) goes into the `tas` file
  instead of the `STUDENTS` columns
- **the course repo prefix, when your names reveal it** — repos named
  `cmpe30-hw1-*` with the assignment named `hw1` leave `cmpe30` as the shared head,
  which is recorded as the classroom's `prefix`; future repos then follow the org's
  existing naming automatically
- **your config updated** — the org is added to `[ORGS]`, and the config file is
  created if you don't have one yet

Re-running is always safe: rows merge, recorded repos are never clobbered, and a rerun
after everything is imported prints `nothing to do`.

## After the import

Discovery works immediately:

```console
$ gh-class-sak classrooms cs101-fall
scanning cs101-fall ...
cs101_fall: hw1
cs101_fall: project
```

```console
$ gh-class-sak repos list cs101-fall project --members --name
TEAM       MEMBERS
team-1     jdoe(Jane Doe),msmith(Marcus Smith)
nightowls  rpatel(Riya Patel),tk-codes
team-3     lchen(Lin Chen)
```

Then finish the job:

1. **Review the imported files.** Clone the `classroom-meta` repo (or read it on
   GitHub): check the tsv rows, and add anyone the TA detection couldn't see to the
   `tas` file — it only detects staff who had write on every repo.
2. **Add classroom settings** you want going forward: a `template` for new repos, and
   branch protection (`protection`, `linear_history`, `force_push`) in `classroom.ini`.
3. **Reconcile.** This creates each classroom's `<classroom>-tas` team with read on all
   its repos, revokes the TAs' leftover per-repo write access, makes each repo's
   collaborators exactly its row's students, and applies the protection settings:

   ```
   gh-class-sak meta apply cs101-fall [--no-dryrun]
   ```

   Run it twice — the second pass prints `nothing to do`.
4. **Verify.** `gh-class-sak help-me-setup` checks the whole chain: token, config,
   each org's classroom-meta, and Canvas.

From here on, the [getting started](getting-started.md) flow applies: new assignments
arrive via `meta assign`, and `meta apply` keeps the org matching the recorded state.
