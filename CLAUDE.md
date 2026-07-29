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

- a CLASSROOM maps to a canvas course and is a directory in its org's meta repository; an org can host several classrooms. the classroom argument matches either side of a `[COURSES]` mapping (canvas course partial = github org), and is used verbatim as an org name when there is no config
- an ASSIGNMENT is the repo name prefix that its repos share. repos are found by listing the org and filtering on that prefix
- a TEAM is the repo name with the assignment prefix stripped off
- use PyGithub to talk to github and GitPython to talk to git. do not hand-roll requests sessions or pagination

# the meta repo

- each org may have a private repo named `meta` recording classroom state: one directory per classroom (normalized canvas partial) with `classroom.ini` ([CLASSROOM] prefix, optional template, optional repo settings), `tas` (one login or email per line), and `students.tsv` (NAME STUDENTS REPO REPO_ID)
- classroom.ini repo settings, all optional: `protection` (none or pr-review — default none, pr-review requires one approving review), `linear_history` (default true), `force_push` (default false)
- in students.tsv the instructor supplies NAME (suffix appended to the classroom prefix) and STUDENTS (comma-joined emails/logins that get write access); the tool fills REPO (url) and REPO_ID (github's permanent numeric id) when it creates the repo, and never clobbers them on re-import
- `meta apply` reconciles reality to the meta for every classroom: creates missing repos (privately, from the template when set), each classroom's TAs go into a `COURSENAME-tas` team added as a read collaborator on that classroom's student repos, students get write on their repos, unlisted non-admin collaborators are revoked. admins are never touched
- `meta apply`/`meta assign` put the effective repo settings on each repo's default branch. a repo created without a template has no branch yet, so its protection lands on the next `meta apply` after the first push. the all-off trio (none/false/true) skips the protection API entirely and existing protection is never removed; free org plans can't protect private repos (warn, don't fail); a protection write replaces hand-set extras like status checks
- discovery honors recorded REPO_IDs, so renamed repos stay tracked

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

- classrooms: list the classrooms and corresponding assignments
    - takes an optional CLASSROOM; without it, lists every org mapped in `[COURSES]`. errors out when neither is given — never enumerate the orgs the token belongs to
    - each assignment will have this format: CLASSROOM: ASSIGNMENT
    - assignments are inferred from repo names: any `-` delimited prefix shared by two or more repos in the org
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
