# Changelog

## v1.0.2

- the TAs moved into `classroom.ini`: a `[TAS]` section, one identity per line,
  replaces the standalone `tas` file. Legacy files are still read, and the next save
  migrates them into the ini and removes the file
- `classroom.ini` gains a `[TEMPLATE]` section — one `ASSIGNMENT = REPO_URL` record
  each — and `meta assign --template REPO_URL` populates it: the URL is validated with
  `git ls-remote` first, and every new repo created for the assignment is seeded from a
  shallow clone of it, pushed as a single fresh commit (content, not history). The
  record also drives repos realized later by `meta apply`, and takes precedence over
  the classroom-wide `template` for its assignment

## v1.0.1

- fix: pending team invitations count as membership. An invited-but-not-accepted TA
  used to be re-invited on every `meta init`/`meta apply` and reported by `meta show`
  as missing; the reconcile now settles to `nothing to do`, and `meta show`'s
  `TAS TEAM` line reports them as `invited, not yet accepted`
- fix: `meta apply CLASSROOM` reconciles only the named classroom; it used to treat the
  argument purely as an org selector and reconcile every classroom in the org. Naming
  the org still reconciles them all
- `meta init` now creates the classroom's TA team right away — members from the `tas`
  entries, read access to the classroom's current repos — instead of leaving that to
  the first `meta apply`. The team's display name is `CLASSROOM-TAs` (GitHub slugs it
  to the same lowercase slug as before, so existing teams keep matching)
- canvas profiles are cached for the session: a roster consulted twice in one run
  (building rows, then resolving emails) fetches each profile exactly once, and a pass
  served entirely from the cache skips its progress bar instead of flashing one
- slow operations show a progress bar (with position and ETA) on stderr: fetching
  canvas profiles, repo members and commit history in `repos list`/`repos members`,
  `meta apply`'s per-repo checks, `meta show`'s membership checks, and the migration's
  collaborator scan. Terminals only — pipes and scripts see nothing
- every dry run now announces itself before anything else:
  `⚠️  dry run: no changes will be made. add --no-dryrun to apply` — so a preview can
  never be mistaken for the real thing
- `meta delete CLASSROOM` removes a classroom from the classroom-meta repo after
  showing its recorded state and confirming — a simple yes when it's empty, typing the
  full name of one of its assignments when it isn't. `--delete-repo` (default:
  `--no-delete-repo`) also deletes the recorded GitHub repos
- `meta init` defaults a new classroom's `prefix` to the classroom argument (made
  repo-name safe) — `meta init f26-cmpe-30` records `prefix = f26-cmpe-30`, so the
  classroom's repos are namespaced by the course out of the box. `--prefix ""` opts
  out, and a re-init never backfills a prefixless classroom (migrated directories may
  embed the prefix in their assignment names)
- identities are now written `EMAIL/GITHUBID`: both halves
  (`joe@example.com/JoeDevExample`), email only (`joe@example.com/`), or GitHub id only
  (`/JoeDevExample`). The syntax applies everywhere ids are recorded — tsv `STUDENTS`
  columns, the `tas` file, Canvas-sourced rows (which now keep both halves), migration
  output — and everywhere they are read: a `/githubid` half is used directly with no
  lookups, an email-only identity resolves via Canvas then the GitHub search API.
  Legacy bare entries still parse (an `@` means an email, anything else a GitHub id)
- fix: Canvas profiles (the source of GitHub ids) are now fetched through the course —
  `/courses/:id/users/:uid` — instead of the account-scoped `/users/:uid`, which most
  installs restrict to admin-or-self and 404 for a teacher token. Previously every
  profile but your own failed with "failed to fetch canvas profile", and GitHub ids
  silently fell back to email search
- `meta assign --from-canvas --assignment NAME` builds the table from the Canvas roster
  instead of a file: one row per enrolled person — students, instructors, and TAs —
  named by their GitHub-safe name (accents stripped, characters a repo name can't hold
  become `-`), carrying their GitHub id from the Canvas profile or their email for the
  usual resolution. `--canvas-group SET` makes it one row per group in that Canvas
  group set, and records the set's name per assignment in `classroom.ini`
  `[GROUP_SETS]`
- `meta init --canvas-course NAME` records the Canvas course's name in
  `classroom.ini`; Canvas lookups prefer it over the classroom directory name
- `meta show` now checks the recorded state against the live org: every student in the
  assignment tables carries a membership marker (✅ collaborator, 📧 invited but not
  yet accepted, ❌ not a collaborator; a legend prints when markers appear), and a
  `TAS TEAM` line reports whether the classroom's `<classroom>-tas` team matches the
  `tas` file, listing missing and extra members
- fix: assignment repos are matched by leading prefix only. The old substring
  fallback meant a prefixless classroom's `assignments` tsv matched every
  `…-assignments-…` repo in the org, listing other classes' repos under their full
  names. Repos that don't carry the `prefix-assignment` naming are still found through
  their recorded ids — which also means a freshly migrated, prefixless classroom now
  lists exactly its recorded repos, with the right team names
- fix: when the classroom argument pins a classroom (`repos list 30 assf`), the
  no-matching-assignment error now lists only that classroom's assignments instead of
  every classroom in the org
- `migrate-github-classroom` now derives the course repo prefix from your answers:
  when every assignment's name is a `-`-suffix of the repo-name prefix it was inferred
  from (repos `cmpe30-hw1-*`, assignment named `hw1`), the shared head (`cmpe30`) is
  recorded as the new classroom's `prefix` — so `prefix-assignment` keeps spelling the
  real repo names and future repos follow the org's existing naming
- migration team names are now always the repo name minus the *inferred* repo prefix,
  so renaming an assignment at the prompt no longer leaves full repo names in the NAME
  column
- new doc: [Migrating from GitHub Classroom](docs/migrating-from-github-classroom.md) —
  where Classroom's bookkeeping lives in the classroom-meta repo, the import
  walkthrough, and the finish-the-job checklist. Linked from the README; the
  getting-started page now points there instead of inlining the migration

## v1.0.0

The release that replaces GitHub Classroom — and the first one on PyPI since v0.2.1,
so everything from v0.3.0 down was never published. If you are coming from the PyPI
version, start with the [README](README.md) and `gh-class-sak help-me-setup`: the
model changed completely when GitHub Classroom was discontinued.

In this version: the config file no longer carries the course list — classroom-meta
*is* the course list. The config keeps only the GitHub orgs and the Canvas credentials.

Breaking changes:

- `[COURSES]` is gone. List your orgs in a new `[ORGS]` section, one per line, and
  delete the mappings. Course names keep working: resolution matches the classroom
  argument against the configured org names first (no meta lookup), then against the
  classroom directories in those orgs' classroom-meta repos. Ambiguity is an error
  listing the candidates.
- `meta init` takes the new course's literal name; the org comes from `--org` (matched
  partially against `[ORGS]`), from the single configured org, or — with no config —
  from the CLASSROOM argument itself, as before. Several configured orgs without
  `--org` is an error.
- naming an org that hosts several classrooms is reported as ambiguous by listing the
  org's classroom directories (the `[COURSES]` mapping used to arbitrate this).

New:

- a startup warning (stderr, terminals only — pipes and scripts stay clean) says this
  is beta code replacing the departing GitHub Classroom; when no orgs are configured a
  second warning notes that, unlike the pre-1.0 versions, the program replaces GitHub
  Classroom rather than working with it, and points at `help-me-setup`
- `gh-class-sak help-me-setup` explains the config file (printing a template when none
  exists) and verifies the whole setup: the github token, each configured org and its
  classroom-meta repo, and the canvas credentials. Read-only; exit 1 when something
  needs attention.
- `gh-class-sak migrate-github-classroom ORG` imports an org left behind by GitHub
  Classroom: assignments inferred from the `ASSIGNMENT-TEAM` repo names (one-off repos
  ignored and listed), then an interactive pass asks which course each assignment
  belongs to (blank skips it) and what to call it — Classroom kept no course marker, so
  only you can attribute them. Each row records the team, its collaborators as
  students, and the repo's url and permanent id — except staff: a login with write on
  every one of a classroom's repos is recorded in the `tas` file instead of the
  `STUDENTS` columns, and re-running the migration repairs rows imported before that
  detection existed. The org is added to `[ORGS]` when missing (the config file is
  created if needed). Merges like `meta assign` — recorded repos are never clobbered —
  under the standard dryrun/no-dryrun pair.

## v0.7.0

The classroom-meta repo is now required. The prefix-inference workarounds for orgs
without one are gone — the repo *is* the model, not an optional layer over it.

Breaking changes:

- `classrooms` and every `repos` command error out (exit 2, pointing at `meta init`)
  when the org has no classroom-meta repo. Previously they fell back to inferring
  assignments from repo-name prefixes.
- the `repos` ASSIGNMENT argument only ever selects an assignment tsv now; an argument
  matching no assignment is an error listing the candidates, instead of being tried as a
  literal repo prefix.
- assignment-prefix inference is removed entirely (`classrooms` no longer guesses
  assignments from `-` delimited repo-name prefixes shared by two or more repos).

To adopt an existing unmanaged org: `meta init` it, then create one `<assignment>.tsv`
per assignment (rows optional — repos matching `prefix-assignment` are found by name).

## v0.6.0

The classroom model becomes explicit: an org hosts a set of classrooms; a classroom is a
directory containing a `classroom.ini` in the org's meta repo; **each `.tsv` file in a
classroom directory is an assignment**, named by its basename. A row's default repo name
joins the non-empty parts of classroom `prefix`, assignment, and `NAME` with dashes; the
recorded `REPO`/`REPO_ID` still always wins once set.

Breaking changes:

- the meta repo is renamed **`meta` → `classroom-meta`**. There is no fallback: a repo
  still named `meta` is simply not seen.
- `students.tsv` is no longer special — it would now be read as an assignment named
  `students`. Assignments live in one tsv each.
- `meta init` no longer infers a prefix from org repo names; `--prefix` is optional and
  simply recorded (unset means repo names start at the assignment segment)
- `meta assign` gains `--assignment NAME`; the default name is the table file's basename
  (`project.tsv` → `project`). The commit message and record output name the assignment.
- the `repos list/members/missing/clone` ASSIGNMENT argument now selects an assignment
  tsv by case-insensitive substring (exact name beats substring). A name that matches in
  several classrooms is an error listing the candidates — name the classroom to pick one.
  Without a classroom-meta repo the argument is the literal repo prefix, as before.
- `classrooms` prints one line per assignment per classroom directory; `meta show` prints
  one table per assignment.

**Migrating an existing org by hand** (the tool does not do this for you):

1. rename the repo: `gh repo rename classroom-meta -R ORG/meta` (renames keep the repo id
   and redirect old URLs)
2. in each classroom directory, rename `students.tsv` to `<assignment>.tsv` and **shorten
   `prefix` so that `prefix-assignment` spells the old prefix** — e.g.
   `prefix = sp26-cmpe-195a-project` becomes `prefix = sp26-cmpe-195a` plus
   `project.tsv`. This keeps every existing repo name matching; skip it and `meta apply`
   drops the old repos from the TA team's universe.
3. delete the stale local checkout under your app dir's `gh-class-sak/meta/` directory

Project infrastructure (no runtime effect):

- the README is now a pitch page — what the tool is and does, with verified examples.
  Usage documentation moved to `docs/getting-started.md` (a walk-through) and
  `docs/commands.md` (the full reference). The console-fence drift test now replays
  every example in `docs/*.md` too, so the moved pages can't go stale either

## v0.5.0

Branch protection for assignment repos, configured per classroom in `classroom.ini`:

- `protection` — `none` (default) or `pr-review` (require one approving review to merge)
- `linear_history` — require a linear history on the default branch (default `true`)
- `force_push` — allow force pushes (default `false`)

`meta assign` and `meta apply` put the effective settings on each repo's default branch:
at creation for repos made from a template, and — since GitHub can't protect a branch
that doesn't exist yet — on the next `meta apply` after the first push for repos created
empty. `meta apply` also repairs drift on every recorded repo, diffing first so a second
run still prints `nothing to do`. Free org plans can't protect private repos; that's a
warning, not a failure. The all-off trio (`none`/`false`/`true`) asks for nothing, skips
the protection API entirely, and never removes existing protection. A protection write
replaces the whole protection object, so hand-set extras (status checks, push
restrictions) don't survive it. `meta show` prints the effective settings.

## v0.4.0

The meta repo: classroom state moves into a private repo named `meta` inside the org. An
org can host several classrooms; each is a directory holding `classroom.ini` (repo
prefix, optional template repo), `tas` (one login or email per line), and `students.tsv`
(`NAME  STUDENTS  REPO  REPO_ID`, where the instructor supplies the first two columns and
the tool records the repo URL and GitHub's permanent numeric id when it creates the repo).

- `meta init` — create the meta repo, record a classroom, seed TAs from Canvas enrollments
- `meta assign` — import a NAME + STUDENTS table (emails resolved to logins, loud error
  when one doesn't resolve), create the repos privately (from the classroom template when
  set), record them, grant the students push. Re-imports never clobber a recorded repo.
- `meta apply` — full reconcile of every classroom: realize hand-added rows, keep each
  classroom's `COURSENAME-tas` team matching its tas file and added with read to that
  classroom's student repos, keep each repo's non-admin collaborators exactly its listed
  students. Admins are never touched; a second run prints `nothing to do`. All of it
  previews under the default dryrun.
- `meta show` — print a classroom's recorded state
- discovery (`repos list/members/missing/clone`, `classrooms`) now consults the meta:
  the classroom prefix anchors assignment matching, and recorded repos are found by their
  permanent id — so repos renamed away from the prefix are no longer invisible. with a
  meta repo, `classrooms` lists classroom directories rather than the org

Project infrastructure (no runtime effect):

- the README now opens with an animated terminal cast, `docs/demo.svg`. It is rendered
  from the same invented course as the console examples (`python -m tests.demo_svg`) and
  drift-tested like them, so it always shows what the CLI really prints
- a dev container (`.devcontainer/devcontainer.json`): one-click contributor setup in
  Codespaces or VS Code, with Python and the dev dependencies preinstalled

## v0.3.0

GitHub Classroom has been discontinued, so the `/classrooms`, `/classrooms/{id}/assignments`,
and `/assignments/{id}/accepted_assignments` endpoints this tool was built on no longer
exist. Repos are now discovered directly from a GitHub org.

Breaking changes:

- `[COURSES]` values are now **GitHub org names** instead of classroom name partials.
  A classroom argument matches either side of the mapping, so `repos list 195A project`
  still works if `CMPE-195A = SJSU-CMPE-195` is configured. With no config at all, the
  classroom argument is used verbatim as the org name.
- the assignment argument is now the **repo name prefix** those repos share, rather than a
  Classroom assignment title. `team` is still the repo name with that prefix stripped.
- `repos missing` without `--group` now reports Canvas students who are not a collaborator
  on any repo, and therefore requires the Canvas config. It previously read the roster from
  Classroom's accepted-assignments data.

Known limitation introduced by this change: repos renamed away from the assignment prefix
are no longer found. Classroom's accepted-assignments data tracked them; prefix discovery
cannot. This is documented in the README.

Other changes:

- replace the hand-rolled `requests` session and pagination with **PyGithub**
- add `repos clone` to clone or fast-forward every repo for an assignment, using **GitPython**.
  Follows the `--dryrun/--no-dryrun` convention: it previews by default and only writes with
  `--no-dryrun`. The token is passed to git through the environment, so it never appears in
  `ps` output, the clone URL, or `.git/config`.
- `classrooms` now lists orgs with their assignment prefixes inferred from repo names
- add a pytest suite covering the pure matching/discovery logic and every command
- drop the direct `requests` dependency

Project infrastructure (no runtime effect):

- CI on GitHub Actions: pytest across Python 3.9-3.14 on Linux plus macOS and Windows at
  the ends of that range, a ruff lint gate, and a job that installs the built wheel into a
  clean environment and drives the CLI from outside the source tree
- issue and PR templates, `CONTRIBUTING.md` with an AI-contribution policy,
  `CONTRIBUTORS.md`, `SECURITY.md`, and Discussions enabled
- the README's example output is generated from `tests/demo.py` and asserted by
  `tests/test_readme.py`, so a sample can no longer drift from what the CLI prints

## v0.2.1

- fall back to GitHub search API (by email, then by name) when instructor Canvas profile has no GitHub link

## v0.2.0

- add `repos members` subcommand to list emails from commit history
- add `--members`, `--instructors`, `--email` flags to `repos list`
- add header row to `repos list` output
- find instructors per group via shared Canvas course sections
- switch Canvas API access to `canvasapi` library
- use GraphQL for enrollment data (roles, names, emails, sections in one query)
- fetch instructor Canvas profiles in parallel
- extract member emails from repo commit history, show both when commit and canvas emails differ
- handle empty repos gracefully

## v0.1.2

- add MIT license and project URLs to PyPI metadata

## v0.1.1

- add README as PyPI long description

## v0.1.0

- initial release
- `classrooms` command to list classrooms and assignments
- `repos list` with aligned columns, `--repo`, `--name`, `--group`, `--show-empty` options
- `repos missing` to find students or Canvas groups without repos
- Canvas LMS integration for group matching via config file
- fuzzy name matching between Canvas and GitHub profiles
