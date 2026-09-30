# Changelog

## Unreleased

- an audit trail: every change the tool makes to who can reach a course's
  repos — repos created or adopted, invitations, revokes, cancelled
  invitations, TA team changes — is appended to the course's `audit.log` in
  the classroom-meta repo with who ran it, the command, and why: the tsv row
  and identity it came from, and whether the GitHub id was read off a Canvas
  profile link. Committed with each run — even a run that stops partway
  commits the entries for what it did; dry runs log nothing
- `course audit COURSE` checks the live repos against the rows: someone with
  access (or an invitation) whom no row lists, one account on rows for
  different people, and — with Canvas — an account that shares no part of the
  enrolled person's name (student, instructor, or TA; any script), or a
  recorded id their Canvas profile no longer links. Each problem comes with
  its fix; exit 1 when there is one. A real `sync` runs it at the end without
  changing its exit status
- `gh-class-sak demo COMMAND...` runs any command on the invented course
  the docs are built on — offline, with nothing kept, so even `--apply` is
  safe to try. `gh-class-sak demo` alone describes the course
- `help-me-setup --create-config` writes the config file: it asks for the
  org and the Canvas details and adds only the sections that are missing.
  At a terminal, a missing config prompts the same offer. `help-me-setup`
  also flags a GitHub token without the `repo` scope, with the fix
- `--apply` is a plain-words synonym for `--no-dryrun`, and the preview
  messages suggest it
- every command's `--help` ends with examples
- `--roster` takes a plain list — one person per line, a repo each — as
  well as the NAME STUDENTS table, and a malformed roster names the line
  and shows both formats instead of a traceback
- `course status COURSE` shows what's done and what's left in a course —
  repos, accepted and pending invitations, the TAs team — with the command
  for each next step
- `course init NEW --like OLD` starts a course from last term's TAs,
  templates, and repo settings
- `repos clone --before DEADLINE` leaves each repo at its last commit
  before the deadline, ready to grade
- `gh-class-sak completion` prints the tab-completion script for bash,
  zsh, or fish
- `--help` lists commands in the order you use them — `help-me-setup`,
  then `course`, `assignment`, `sync` — instead of alphabetically; so do
  `course --help` (`init` first) and `repos --help`
- `course init` adds the org to the config's `[ORGS]` when it isn't there,
  so every later command finds the course without `--org`
- a dry run that previewed anything now ends with `that was a preview:
  nothing changed. add --no-dryrun to apply` — a long preview scrolls the
  opening banner away
- `sync`, `assignment create`, `course ta`, and `course settings` end with a
  one-line summary: what changed (or would) by kind, and how many warnings
  and errors were printed. After a real run, `course init` and
  `assignment create` name the next step
- `course ta add/remove COURSE IDENTITY...` changes the course's TAs — the
  `[TAS]` record and the TAs team together — and `course settings COURSE`
  shows or changes the repo settings (branch protection, template) and
  applies new protection to every recorded repo right away. Neither needs
  a hand edit of `classroom.ini`
- the commands speak of **courses**, not classrooms, and are named for what
  they do: `course init`, `course list`, `course show`, `course delete`,
  `assignment create COURSE NAME` (with `--roster FILE` or `--from-canvas`),
  and `sync`. The top-level `--help` defines the words — a course is one
  Canvas course hosted in a GitHub org; an assignment is one repo per
  student or group — and the path from `course init` to `sync`
- a `COURSE` argument of the new commands is always a course, never an org:
  it is looked up in `--org`, or in every org in `[ORGS]`, with an exact name
  beating a partial one. An org name typed where a course belongs says to
  pass it as `--org`; `sync --org ORG` syncs every course in the org
- `assignment create` only touches its own assignment's repos (plus the TA
  team's read on them); everything else across the course — other
  assignments, TA team membership — is `sync`'s job. `meta assign` keeps
  converging the whole classroom
- the old commands (`meta init/list/show/delete/assign/apply` and
  `classrooms`) still work unchanged but are hidden from `--help`; at a
  terminal each says which command replaced it. Messages throughout now
  point at `course init` and `sync`. The stored names — the `classroom-meta`
  repo, `classroom.ini` and its `[CLASSROOM]` section — are unchanged, so
  existing orgs keep working as they are
- a default repo name longer than GitHub's 100-character limit is cut off at
  100 instead of failing the create with a traceback
- a row whose repo name another row already holds — two long names that cut
  to the same 100 characters, or a repo another row recorded, in any course
  in the org — gets the first free numbered name (`…-2`, `…-3`) instead of
  silently sharing that repo, and the run says which. A prefix and
  assignment that leave no room for team names are a clear error
- two people (or two Canvas groups) with the same name get numbered rows,
  `Jose-Nunez` and `Jose-Nunez-2`: before, the second replaced the first's
  row and one student was left with no repo. Each keeps their own row on
  every re-import, however Canvas orders them

## v1.5.0

- a missing `classroom-meta` repo no longer reads as "the course isn't set up".
  GitHub 404s a private repo the token can't see exactly like one that was never
  created, so the error now offers both readings and names the token: who it
  authenticates as, its scopes, and the likely fix — the `repo` scope for a
  classic token, an org resource-owner grant for a fine-grained one, or org
  membership and SAML SSO authorization when the scope is already there. A
  `classroom-meta` repo that is present but records no classrooms, or that
  can't be checked out, now says so instead of claiming it is missing

## v1.4.0

- `meta assign --from-canvas` now notices recorded rows whose person (or
  group) has left the Canvas roster: it warns about each by default, and the
  new `--remove-dropped` flag removes the rows instead. A removed row's repo
  is left in place (each one is named in a warning) — only the record and
  the TA team's read grant go away. An enrollee whose Canvas entry has
  neither an email nor a GitHub link is never treated as dropped

## v1.3.0

- `meta assign` now converges the whole classroom after its import, exactly
  as `meta apply` would: students missing from a recorded repo are invited,
  unlisted collaborators are warned about (the new
  `--remove-unlisted-contributors` flag revokes them, with apply's safety
  hold when an identity doesn't resolve), empty recorded repos get the
  welcome commit, drifted branch protection is re-applied, and the TA team
  reconciles even when `[TAS]` is empty
- the docs gained a "when to assign, when to apply" note, a
  `canvas message-missing` section on the Canvas integration page, and
  README coverage of roster-built assignments and straggler messaging

## v1.2.1

- `meta apply` no longer re-grants push to a listed student who is already
  an admin on the repo (the instructor on their own row): github answers
  that grant with a no-op, so it repeated on every run without ever
  converging. Admins now count as present alongside collaborators and
  pending invitees — and stay untouched in both directions

## v1.2.0

- empty repos are seeded with a `WELCOME.md` initial commit ("Welcome to
  CLASSROOM! You will submit your assignments here using git commit and git
  push.") by both `meta assign` (repos it creates or adopts without a
  template) and `meta apply` (any recorded repo with no default branch), so
  the branch exists and the classroom's protection lands in the same run
  instead of waiting for the first student push
- messages printed while a progress bar is up no longer tear the bar apart:
  the latest is shown at the end of the bar's line (clipped to fit, staying
  up until the next message replaces it) and every held message prints for
  real — colors, streams, and order intact — when the bar finishes

## v1.1.2

- the no-github-link message now says the Canvas profile link's name (Title)
  must be exactly `github`, alongside the profile URL
- `meta apply --help` explains that a student listed on a repo's row but not
  yet a collaborator is invited (granted push)
- `meta assign --help` explains that new repos' students are invited as
  collaborators, but a row whose repo is already recorded is skipped —
  `meta apply` adds missing collaborators to existing repos

## v1.1.1

- the accept-your-invitation message ends with a note that a 404 on the
  invitation link means you aren't logged in to GitHub (or are logged in as
  the wrong account)
- every `canvas message-missing` message closes with a bold do-not-respond
  footer: the messages are informational

## v1.1.0

- Canvas's Student View "Test Student" is excluded from every roster the tool
  builds: it enrolls with role StudentEnrollment but is not a person — it broke
  `canvas message-missing --no-dryrun` (Canvas refuses it as a recipient) and got
  phantom rows from `meta assign --from-canvas`
- fix: a Canvas send failure in `canvas message-missing` is a held per-student
  error printed at the end (exit 1), not a crash that aborts the remaining sends

- GitHub's own route names (`dashboard`, `settings`, `notifications`, …) are never
  treated as usernames: a Canvas link to `github.com/dashboard` — the address bar
  pasted while signed in — is not recorded as an id by `--from-canvas`, resolves to
  nothing when already recorded, and `canvas message-missing` flags it as a bad link
  without needing a lookup
- fix: a recorded github id that doesn't exist (a typo'd login) no longer crashes
  `meta apply`/`meta assign` with a traceback and aborts every grant after
  it. The 404 on the grant — student push, or TA team membership — degrades
  to a loud per-person error, the rest of the run completes, and the run
  exits 1
- new `canvas message-missing CLASSROOM ASSIGNMENT` subcommand: sends each stranded
  student a Canvas message saying exactly what to do — add the missing GitHub link to
  their Canvas profile, fix a link that points at a nonexistent GitHub account, or
  accept the still-pending invitation to their assignment repo. Collaborators are
  left alone; a student with a working GitHub account but neither access nor an
  invitation is a loud error pointing at `meta apply` (exit 1), not a message; the
  dry run (default) lists who would get which message and prints the full texts
- the GitHub search API is no longer used to resolve an email to a GitHub id — an
  email-only identity now resolves via the Canvas profile's GitHub link or not at
  all. The search only ever matched a student who publicly listed that exact email
  on their GitHub profile (nearly none do), its loose token matching could return
  strangers, and its 30-requests-a-minute rate limit slowed every roster-sized run.
  Migration note: an identity that used to resolve through a public profile email
  now needs its `/githubid` half recorded in the tsv, or the GitHub link added to
  the student's Canvas profile
- new `meta list [CLASSROOM]` subcommand: one row per recorded classroom — prefix, TA
  count, and each assignment with its team count — read straight from the
  classroom-meta repo, with no live-org checks. Without an argument it lists every
  configured org; the argument names an org or a single classroom

## v1.0.3

- a display name is never used to resolve a GitHub id: the search fallback for a
  person whose Canvas profile has no GitHub link is now email-only. Two people can
  share a name, and an id that ends up granting repo access must not come from a
  lookalike match. (Name matching still powers the read-only reports — group and
  instructor columns, `repos missing` — where a wrong guess can't grant anything)

## v1.0.2

- fix: every GitPython repo handle is closed deterministically — on Windows an open
  handle pins files inside the classroom-meta checkout, breaking cleanup
- the `meta apply` sync contract is now specified precisely in the commands
  reference: the four passes, what a run writes back, what it never does, and the
  exit codes
- the test suite no longer sees ambient credentials, so a test that would reach the
  real token fails at the desk instead of only on CI
- fix: an unresolved identity never triggers revocation. `meta apply` used to
  reconcile a row's collaborators against whatever subset of its students happened to
  resolve, so a transient failure (a removed Canvas profile link, a search rate limit)
  could revoke a real student's write access. Rows with unresolved identities now
  leave collaborators untouched — loudly — and the run still exits 1
- fix: assignment prefixes match at a `-` boundary, so `hw1` no longer captures
  `hw10`'s repos (with mangled team names) in `repos list`/`repos clone`, or in the
  set of repos `meta apply` grants the TA team read on
- removing people is now opt-in: `meta apply` warns about collaborators (and pending
  invitations) the assignment rows don't list instead of revoking them; the new
  `--remove-unlisted-contributors` flag restores the revoke. Migrations note: demoting
  Classroom-era TAs' leftover per-repo write now needs the flag
- fix: repo collaborator reconcile understands pending invitations — an
  invited-but-not-accepted student is not re-invited on every apply, and removing a
  student from the tsv cancels their pending invitation so they can't still accept
  and gain write. The test fakes now model GitHub's invite-on-add behavior
- fix: a `%` in a recorded value (a url-encoded template REPO_URL, a Canvas token) is
  data, not a parse error that bricks the file on every later load; hand-edit
  mistakes that raise configparser's own errors degrade to a warning or a clean exit
  instead of a traceback, and `migrate-github-classroom` no longer corrupts a config
  whose `[ORGS]` header carries an inline comment
- fix: GitHub lookups return "not found" only on a real 404 — a transient error exits
  with the message instead of reading as "recorded repo is gone" or "no
  classroom-meta repo" — and the search-api resolvers warn loudly on a rate limit
  instead of reporting everyone past the cutoff as unresolvable
- fix: `meta assign --from-canvas` prefers the recorded `canvas_course` over the
  resolved directory name, matching `meta init` and `meta apply`
- fix: `meta show` marks email-only identities by who they resolve to, so a
  `jane@sjsu.edu/` entry with access shows ✅ instead of a false ❌ (and the
  `TAS TEAM` line stops reporting its member as both missing and extra)
- fix: `repos list --email/--instructors/--group` degrade gracefully with an
  `[ORGS]`-only config (what the migration creates) instead of exiting on the
  missing Canvas credentials
- fix: saves rewrite only the assignments that changed, so hand-written `#` comments
  in an untouched assignment's tsv survive an assign/apply/migrate of another
- fix: `classrooms CLASSROOM` lists just the classroom it names, not its whole host
  org
- fix: `migrate-github-classroom` no longer records the entire roster as TAs when one
  group owns every repo — when everyone is on every repo there is no staff signal,
  so it warns and records everyone as students
- template seeding is robust: an unreachable template fails with a clean error,
  deletes the empty shell it created (so a re-run retries instead of adopting an
  unseeded repo), and pushes to the repo's default branch instead of a hardcoded
  `main`
- `meta assign` reconciles the classroom's TA team in the same run, so repos it
  creates are TA-readable immediately; and `--template` with `--assignment` but no
  table records or updates a template without re-supplying the roster
- `repos members` labels its first column `TEAM` (it always held team names)
- two new docs: [Canvas integration](docs/canvas-integration.md) — how GitHub ids map
  to Canvas accounts, and assignments built from enrollments or group sets — and
  [The classroom-meta files](docs/classroom-meta-files.md) — the file layouts, the
  formats, and how TA teams manage the TAs. Both linked from the README; the demo
  course's recorded rows now use the identity syntax, so `meta show`'s documented
  output teaches it
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
