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

- for commands that change something, use a `--dryrun/--no-dryrun` flag pair defaulting to dryrun. the bare command just prints what would happen with a ⚠️ in front; `--no-dryrun` applies the change

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

- each org may have a private repo named `classroom-meta` recording classroom state: one directory per classroom with `classroom.ini` ([CLASSROOM] optional prefix, optional template, optional repo settings), `tas` (one login or email per line), and one `<assignment>.tsv` per assignment (NAME STUDENTS REPO REPO_ID)
- classroom.ini repo settings, all optional: `protection` (none or pr-review — default none, pr-review requires one approving review), `linear_history` (default true), `force_push` (default false)
- in an assignment tsv the instructor supplies NAME and STUDENTS (comma-joined emails/logins that get write access); the tool fills REPO (url) and REPO_ID (github's permanent numeric id) when it creates the repo, and never clobbers them on re-import
- `meta init CLASSROOM [--org ORG]` records the literally-named new course; the org is the single `[ORGS]` entry, the partially-matched `--org`, or — with no config — the classroom argument itself. several configured orgs without `--org` is an error
- `meta assign CLASSROOM TABLE [--assignment NAME]` imports a table as the assignment named by the flag or, by default, the table file's basename
- `meta apply` reconciles reality to the meta for every classroom and assignment: creates missing repos (privately, from the template when set), each classroom's TAs go into a `COURSENAME-tas` team added as a read collaborator on that classroom's student repos across all its assignments, students get write on their repos, unlisted non-admin collaborators are revoked. admins are never touched
- `meta apply`/`meta assign` put the effective repo settings on each repo's default branch. a repo created without a template has no branch yet, so its protection lands on the next `meta apply` after the first push. the all-off trio (none/false/true) skips the protection API entirely and existing protection is never removed; free org plans can't protect private repos (warn, don't fail); a protection write replaces hand-set extras like status checks
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

- help-me-setup: explain the config file (print a template when none exists) and verify the setup: github token, each configured org and its classroom-meta repo, canvas credentials. read-only, exit 1 when something needs attention
- migrate-github-classroom: takes an ORG; scans its Classroom-era repos (named ASSIGNMENT-TEAM), infers the assignments from shared name prefixes, then prompts per assignment for the course it belongs to (blank skips) and its name (default: the prefix). records one tsv per assignment under the chosen course's classroom dir — collaborators as students, repo url and permanent id filled in. a login with write on every one of a classroom's repos (>=2 repos) is a TA: excluded from STUDENTS and recorded in the classroom's tas file instead. when every assignment name is a `-`-suffix of its inferred repo prefix, the shared head is recorded as the new classroom's `prefix` (teams always strip the inferred repo prefix, whatever the assignment is named). adds the org to the config's [ORGS] when missing (creating the file if needed); merges like `meta assign` and never clobbers recorded repos; standard dryrun pair with prompts asked before the preview
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
