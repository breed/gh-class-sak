# Changelog

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
