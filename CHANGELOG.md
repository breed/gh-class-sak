# Changelog

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
