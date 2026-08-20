# project description

a swiss army knife for managing github classrooms now the official github classrooms is gone.

# language

- python to be deployed via pypi
- click for commandline parsing

# testing

- pytest, run with `pytest`. install the dev extra with `pip install -e ".[dev]"`
- github and canvas are stubbed in `tests/fakes.py`, so the suite runs offline. never let a test reach the network
- when fixing a bug, reproduce it first and add a failing test before the fix

# repo hygiene

- this project follows the "repo to product" tips. the `repo-audit` and `repo-upgrade` skills from https://github.com/breed/repo-to-product are the source of truth
- run `repo-audit` before a release and after any change to packaging, docs layout, or CI
- keep docs in the Diátaxis layout the skill expects: tutorial, how-to, reference, explanation

# common flags

- slow per-repo/per-person loops iterate through `core.progress(items, label)` — a stderr progress bar that is a plain passthrough when stderr is not a tty, so pipes, fences, and tests see nothing
- for commands that change something, use a `--dryrun/--no-dryrun` flag pair defaulting to dryrun. the bare command just prints what would happen with a ⚠️ in front; `--no-dryrun` applies the change. a dry run announces itself first: `⚠️  dry run: no changes will be made. add --no-dryrun to apply` (implemented centrally in core.dryrun_option's callback)

# how classrooms and assignments are identified

github classroom is gone, so nothing may call `gh classroom` or the `/classrooms` and `/assignments` REST endpoints.

- a github ORG hosts a set of classrooms
- a CLASSROOM is a directory containing a `classroom.ini` in its org's `classroom-meta` repo, named by the normalized canvas course partial it maps to. the config's `[ORGS]` section lists the github orgs, one per line — the course list itself lives in classroom-meta, never in the config. the classroom argument matches a configured org by name first (no meta lookup), else a classroom directory found in the configured orgs' classroom-meta repos; it is used verbatim as an org name when there is no config
- an ASSIGNMENT is a `.tsv` file in a classroom directory, named by its basename. the classroom-meta repo is required: commands that read a classroom error out (pointing at `meta init`) when the org has none — there is no prefix-inference fallback
- an assignment's repos are found by their name prefix (the prefix-assignment join) plus the recorded REPO_IDs
- a TEAM is the repo name with the assignment's repo prefix stripped off
- the default repo name joins the non-empty parts of the classroom prefix, the assignment, and the row NAME with `-` (the prefix is optional); a recorded REPO/REPO_ID always wins over the default name
- use PyGithub to talk to github and GitPython to talk to git. do not hand-roll requests sessions or pagination

# the classroom-meta repo

- each org may have a private repo named `classroom-meta` recording classroom state: one directory per classroom with `classroom.ini` and one `<assignment>.tsv` per assignment (NAME STUDENTS REPO REPO_ID). classroom.ini carries everything else: [CLASSROOM] optional prefix/template/settings, [TAS] one identity per line, [TEMPLATE] one ASSIGNMENT = REPO_URL per record, [GROUP_SETS] one ASSIGNMENT = SET per record. a legacy standalone `tas` file is still read and removed on the next save
- classroom.ini repo settings, all optional: `protection` (none or pr-review — default none, pr-review requires one approving review), `linear_history` (default true), `force_push` (default false)
- identities are written EMAIL/GITHUBID: both halves `joe@example.com/JoeDevExample`, email only `joe@example.com/`, github id only `/JoeDevExample`. legacy bare entries still parse (an @ means an email, anything else a github id), but the tool always writes the slash syntax
- in an assignment tsv the instructor supplies NAME and STUDENTS (comma-joined identities that get write access); a `/githubid` half is used directly, an email-only identity is resolved via canvas only (the profile's github link) — the github search api is never used. the tool fills REPO (url) and REPO_ID (github's permanent numeric id) when it creates the repo, and never clobbers them on re-import
- `meta init CLASSROOM [--org ORG] [--canvas-course NAME]` records the literally-named new course; the org is the single `[ORGS]` entry, the partially-matched `--org`, or — with no config — the classroom argument itself. several configured orgs without `--org` is an error. `--canvas-course` records the canvas course name in classroom.ini and canvas lookups prefer it over the directory name. a NEW classroom's prefix defaults to the github-safe classroom argument (`--prefix ""` opts out); a re-init keeps the recorded prefix and never backfills a prefixless classroom. init also creates the classroom's `CLASSROOM-TAs` team (github slugs the name to lowercase; lookups use the slug) with the tas as members and read on the classroom's current repos — usually none yet
- `meta assign CLASSROOM TABLE [--assignment NAME]` imports a table as the assignment named by the flag or, by default, the table file's basename
- `meta assign --template REPO_URL` validates the url with git ls-remote (exit 2 when unreachable), records it in [TEMPLATE] for the assignment, and new repos for that assignment are seeded from a shallow clone of it pushed as a single fresh commit (no template history) on the repo's default branch. the [TEMPLATE] record takes precedence over the classroom-wide `template` for its assignment. with `--assignment` it works without a table, recording the template alone; an unreachable template at realize time errors, deletes the empty shell, and exits 1 so a re-run retries. assign also reconciles the classroom's TA team (when [TAS] has entries), so repos it creates are TA-readable immediately
- `meta assign CLASSROOM --from-canvas --assignment NAME [--canvas-group SET]` builds the table from canvas instead: one row per enrolled person (students, instructors, and TAs), NAME = the person's github-safe name (accents stripped, invalid chars become `-`), entry = their EMAIL/GITHUBID identity with both halves as far as canvas knows them. with `--canvas-group`, one row per group in that canvas group set, and the set's name is recorded per assignment in classroom.ini `[GROUP_SETS]`
- `meta apply` reconciles reality to the meta — the named classroom only, or every classroom when the argument names the org. per classroom and assignment: creates missing repos (privately, from the template when set), each classroom's TAs go into a `CLASSROOM-TAs` team added as a read collaborator on that classroom's student repos across all its assignments, students get write on their repos. unlisted non-admin collaborators (and their pending invitations) are warned about and left alone; `--remove-unlisted-contributors` revokes them instead. admins are never touched either way
- `meta apply`/`meta assign` put the effective repo settings on each repo's default branch. a repo created without a template has no branch yet, so its protection lands on the next `meta apply` after the first push. the all-off trio (none/false/true) skips the protection API entirely and existing protection is never removed; free org plans can't protect private repos (warn, don't fail); a protection write replaces hand-set extras like status checks
- `meta delete CLASSROOM [--delete-repo]` shows the classroom's recorded info then confirms: a simple yes for an empty classroom, typing the full name of one of its assignments otherwise. removes the classroom directory from classroom-meta; `--delete-repo` (default off) also deletes the recorded github repos. the tas team is left alone. standard dryrun pair, confirmation prompts run in both modes
- `meta list [CLASSROOM]` prints one table row per recorded classroom — CLASSROOM, PREFIX, TAS (count), and ASSIGNMENTS as name(teams) — straight from the classroom-meta repos with no live-org checks. without an argument it walks every `[ORGS]` org like `classrooms`; the argument names an org or a single classroom. empty cells show `-`
- `meta show` checks the recorded state against the live org: each student is marked ✅ (collaborator), 📧 (invited, not accepted), or ❌ (not a collaborator) — rows without a repo stay unmarked — and a TAS TEAM line reports whether the `<classroom>-TAs` team matches the [TAS] section (missing/extra members listed)
- discovery honors recorded REPO_IDs, so renamed repos stay tracked; the repos ASSIGNMENT argument selects an assignment tsv by case-insensitive substring, exact name wins over substring hits, and a name matching in several classrooms is an error

# getting information about instructors and students

### listing student and instructor names, emails, and relationships

- find students and instructors of a section using this graphQL. instructors of a student share a courseSectionId with that student
    ```
    query MyQuery {
      course(id: "COURSEID") {
        name
        enrollmentsConnection {
          nodes {
            role {
              name
            }
            user {
              id
              name
              email
            }
            courseSectionId
          }
        }
      }
    }
    ```

### determine github information for students and instructors

find the github ids of all the students and instructors using the canvas REST API to get the profile for the given user id and look for the github link

# subcommands

- canvas message-missing: takes a CLASSROOM and ASSIGNMENT; sends a canvas conversation to each enrolled student stranded on the way to their assignment repo, in three categories — no-link (no github link on the canvas profile), bad-link (the linked github account doesn't exist), invited (an unaccepted repo invitation, message names the repo url). collaborators are never messaged; a student with a working github account but neither repo access nor a pending invitation is a loud error to the instructor (exit 1) pointing at `meta apply`, never a message to the student. needs the canvas config. standard dryrun pair; the dry run lists recipients and prints the full message texts (templates live at the top of commands/canvas.py). each send is a new conversation (force_new), never an append to an old thread
- help-me-setup: explain the config file (print a template when none exists) and verify the setup: github token, each configured org and its classroom-meta repo, canvas credentials. read-only, exit 1 when something needs attention
- migrate-github-classroom: takes an ORG; scans its Classroom-era repos (named ASSIGNMENT-TEAM), infers the assignments from shared name prefixes, then prompts per assignment for the course it belongs to (blank skips) and its name (default: the prefix). records one tsv per assignment under the chosen course's classroom dir — collaborators as students, repo url and permanent id filled in. a login with write on every one of a classroom's repos (>=2 repos) is a TA: excluded from STUDENTS and recorded in the classroom's [TAS] section instead — unless everyone is on every repo (one group owning all the repos), which warns and records everyone as students. when every assignment name is a `-`-suffix of its inferred repo prefix, the shared head is recorded as the new classroom's `prefix` (teams always strip the inferred repo prefix, whatever the assignment is named). adds the org to the config's [ORGS] when missing (creating the file if needed); merges like `meta assign` and never clobbers recorded repos; standard dryrun pair with prompts asked before the preview
- classrooms: list the classrooms and corresponding assignments
    - takes an optional CLASSROOM; without it, lists every org in `[ORGS]`. errors out when neither is given — never enumerate the orgs the token belongs to
    - each assignment will have this format: CLASSROOM: ASSIGNMENT
    - classrooms and assignments come from the classroom-meta repo: one line per assignment tsv per classroom directory
- repos list: takes a CLASSROOM and ASSIGNMENT and lists each repo
    - output is space-padded columns with a header row: TEAM always, then REPO, MEMBERS, INSTRUCTORS, GROUP depending on flags; the last column is never padded
    - members are comma-joined repo collaborators excluding admins; `--name`/`--email` annotate each as LOGIN(NAME,EMAIL)
    - if the `--alt` flag is given, any alternative repo names (previous names for the repo) will be shown as an extra column
- repos members: list the members of each repo with names and emails mined from commit history
- repos missing: list canvas students, or canvas groups with `--group`, that have no repo
- repos clone: clone or fast-forward every repo for an assignment. pass the token to git through the environment so it never lands in argv, the clone url, or `.git/config`
- repos update: takes a file with the same format as `repos list` that will update the repo with the give members and admins
    - if any of the ids are emails, first resolve the email to the github id. print a noticeable error if the email does not resolve

# not yet implemented

- `repos update` and the `--alt` flag on `repos list`
