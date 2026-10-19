# AGENTS.md

Guidance for AI assistants working in this repo. An instructor usually brings
you here for one of two jobs, often in the same session:

1. **Running a course with the tool**: syncing repos, onboarding students and
   TAs, and reading the tool's output for them.
2. **Changing the tool**: fixing a bug they hit, or adding something they need.

The code and design rules for the second job live in [CLAUDE.md](CLAUDE.md).
They apply to every agent, not only Claude: read them before you change code.
This file is about working *with* the instructor.

## Ground rules

- **Preview first, apply only with a yes.** Every command that changes
  something is a dry run unless given `--apply`. Run the preview, show the
  instructor what would change, and add `--apply` only after they agree.
- **Never run these unless the instructor explicitly asks for that exact
  action:**
  - `--remove-unlisted-contributors`, which revokes people's access
  - `--remove-dropped`, which drops roster rows
  - `course delete`, and above all with `--delete-repo`
  - deleting a repo on GitHub, or editing the classroom-meta repo by hand

  The tool's own audit suggests `--remove-unlisted-contributors` as a fix.
  Check what the warning is about before you pass that on. A TA reaching
  repos through a team was once flagged on every repo, and that fix would
  have tried to revoke them.
- **Real student data stays out of the code.** Names, emails, GitHub ids and
  group names from a real course must never appear in tests, commits, PRs,
  issues or docs. Use invented ones (`jane@school.edu/janedoe`, `Team-A`,
  `Ada-de-Lee`), and search your diff for real names before committing.
- **Suspect the tool, not the people.** When output looks wrong, such as
  dozens of identical warnings or a person flagged who obviously belongs,
  find out why before telling the instructor to act on it. Read the code,
  query GitHub or Canvas read-only, and reproduce it in a test.

## Installing and updating

```bash
# the latest main (what the instructor normally runs)
uv tool install --force --reinstall "git+https://github.com/breed/gh-class-sak@main"

# an unmerged local branch, to try a fix before it's merged
uv tool install --force --reinstall /path/to/gh-class-sak
```

Reinstall from `main` once the fixes are merged, so the instructor isn't left
on a test build. `gh-class-sak help-me-setup` checks the config, the GitHub
token, each org's classroom-meta repo and the Canvas credentials.

## The model in one minute

- A **course** is a directory in the org's private `classroom-meta` repo. It
  holds a `classroom.ini` (TAs, template, Canvas group sets) and one
  `<assignment>.tsv` per assignment, with columns `NAME STUDENTS REPO REPO_ID`.
- The COURSE argument matches course directories by partial name, so `CMPE`
  may be enough. Add `--org ORG` when the config doesn't list the org.
- **Identities** are written `EMAIL/GITHUBID`: `jane@school.edu/janedoe`,
  `/janedoe` (GitHub id only) or `jane@school.edu/` (email only). An email-only
  identity works only once the person's Canvas profile links their GitHub
  account; the GitHub search API is never used.
- Repos are tracked by their **permanent REPO_ID**, so renaming a repo on
  GitHub never loses it.
- TAs get read access through a `COURSE-TAs` team; students get write access
  as direct collaborators.

## Common tasks

| The instructor wants to… | Run (preview first, then add `--apply`) |
|---|---|
| see what's left to do | `gh-class-sak course status COURSE` |
| check who has access against who should | `gh-class-sak course audit COURSE` |
| create or refresh group repos from Canvas | `gh-class-sak assignment create COURSE NAME --from-canvas --canvas-group "SET"` |
| one repo per enrolled person | `gh-class-sak assignment create COURSE NAME --from-canvas` |
| bring every repo in line with the record | `gh-class-sak sync COURSE` |
| nudge students with no or bad GitHub links | `gh-class-sak canvas message-missing COURSE NAME` |
| add a TA | `gh-class-sak course ta add COURSE email/githubid` |
| give an existing TA their GitHub id | `course ta remove COURSE email`, then `course ta add COURSE email/githubid` |
| collect submissions at a deadline | `gh-class-sak repos clone COURSE NAME --dest DIR --before "YYYY-MM-DD HH:MM"` |

- **Students without a GitHub link:** run `canvas message-missing`. It sends
  a Canvas message to each one, with no email needed. After they add the link
  to their Canvas profile, run `sync --apply` to invite them.
- **A group wants its repo renamed:** the tool doesn't rename repos. Rename it
  on GitHub (`gh repo rename -R ORG/OLD NEW`, giving only the new name). The
  next `sync --apply` updates the recorded URL.
- **A Canvas group was renamed:** a re-import recognizes it (at least half the
  members shared, or only the capitalization changed), keeps its repo and says so. `sync` itself
  never reads Canvas group names.
- **A duplicate repo was created by mistake:** confirm with the instructor
  which one is real. Deleting needs a token with the `delete_repo` scope; the
  instructor grants it with `gh auth refresh -s delete_repo` and can remove it
  afterwards with `gh auth refresh -r delete_repo`. Remove the duplicate's row
  from the assignment tsv in classroom-meta, matching on both NAME and REPO_ID.
  Then preview `assignment create` again to confirm nothing would be recreated.

## Reading `sync` output

| Line | Meaning | Usually |
|---|---|---|
| `cannot resolve "x@school.edu/" … to a github id` | no GitHub link on their Canvas profile | `canvas message-missing` |
| `NAME: inviting the members it can resolve; removals wait…` | a group with an unresolved member; the rest are still invited | nothing, it clears once they link |
| `cannot read the canvas profile of NAME (Not Found)` | Canvas won't show that profile, often a staff member's | harmless unless that person is on a roster |
| `cannot resolve TA "x@school.edu/"` | a TA recorded by email only | record their GitHub id (see above) |
| `unlisted collaborator X on REPO` | someone was added to the repo directly, outside the record | ask the instructor; never auto-revoke |
| audit: `X is named "…" on GitHub, but Canvas has them as "…"` | the GitHub display name shares nothing with the Canvas name | often a nickname; ask before changing anything |
| `summary:` / `summary (preview):` | counts of changes, warnings and errors | the line to report back |

A `sync` over about 50 repos takes several minutes. Run it with a generous
timeout, or in the background, and save the output to a file so you can read
all of it.

## Reading the record directly

To see exactly what's recorded, clone the classroom-meta repo over HTTPS
into a scratch directory. An SSH clone can hang waiting for a passphrase.

```bash
timeout 60 git clone --depth 5 https://github.com/ORG/classroom-meta /tmp/scratch/meta
```

Treat that copy as read-only. Each course's `audit.log` records every access
change the tool has made: who made it, when, and why.

## Changing the tool

Follow [CLAUDE.md](CLAUDE.md). In practice:

- **Test first.** Reproduce the bug in a test that fails, then fix it. GitHub
  and Canvas are faked in `gh_class_sak/fakes.py`, and tests never touch the
  network. When the fake doesn't behave like the real API, fix the fake first:
  a bug that hid in the gap between them will hide again.
- **One branch and PR per fix, each from `origin/main`.** Don't stack a PR on
  another PR's branch: merging it lands in that branch, not in `main`.
- **Before pushing:** run `pytest` and `ruff check .`, add a CHANGELOG entry
  under Unreleased, and update CLAUDE.md when behavior changes.
- **When you can, check the fix against the real course with a dry run** (for
  example a `sync` preview from the branch's venv), and report the before and
  after numbers.
- **After CI**, read the review comments, fix them with tests, and reply to
  each one saying what changed and in which commit. A merge conflict with
  `main` is usually just the CHANGELOG: rebase and keep both entries.

## Working in the instructor's terminal

- When they need to run something interactive themselves (a `gh auth`
  login or scope change), suggest typing it with a leading `!` in the prompt.
  There must be no space before the `!`.
- Their shell is often zsh. Quote `$var:...` as `${var}:...` (zsh treats
  `:r` and the like as modifiers), and don't loop over a word list to build
  multi-word commands.
