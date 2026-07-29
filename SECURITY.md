# Security policy

## Reporting a vulnerability

Please report privately via [GitHub Security Advisories][advisory] rather than opening a
public issue.

[advisory]: https://github.com/breed/gh-class-sak/security/advisories/new

## Supported versions

The latest release on PyPI is the only supported version.

## What this tool has access to

Worth knowing before you run it, and worth keeping in mind if you're contributing:

- **A GitHub token** with org and repo access, read from `GH_TOKEN` or `gh auth token`.
  `repos clone` hands this to git through `GIT_CONFIG_*` environment variables so it never
  reaches argv, the clone URL, or a checked-out `.git/config`. Any change to that code
  path should preserve that property.
- **A Canvas API token**, read from the `[CANVAS]` section of the config file. Treat that
  file as a secret — it is not encrypted.
- **Student names, emails, and GitHub handles**, from Canvas and from repo commit history.
  Please never paste these into an issue or a test fixture.

`gh-class-sak` makes no outbound calls other than to GitHub, to your configured Canvas
instance, and to the git remotes of repos you ask it to clone.
