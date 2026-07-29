# Changelog

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
