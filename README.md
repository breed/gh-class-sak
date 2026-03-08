# gh-class-sak

A command-line Swiss Army Knife for managing GitHub Classrooms, with optional Canvas LMS integration for group matching.

## Installation

```bash
pip install gh-class-sak
```

Requires Python 3.9+.

## Authentication

### GitHub

The tool uses your GitHub token, resolved in this order:

1. `GH_TOKEN` environment variable
2. `gh auth token` (GitHub CLI)

### Canvas (optional)

For `--group` features, create a config file at `~/.config/gh-class-sak.ini`:

```ini
[CANVAS]
url = https://your-canvas-instance.instructure.com
token = YOUR_CANVAS_API_TOKEN

[COURSES]
CMPE-142 = sp26-142
CMPE-195A = 195A
```

The `[COURSES]` section maps Canvas course name partials (keys) to GitHub classroom name partials (values). Matching is case-insensitive and treats hyphens, underscores, and spaces as equivalent.

## Usage

### classrooms

List all classrooms and their assignments.

```
gh-class-sak classrooms
```

Output format: `CLASSROOM: ASSIGNMENT`

### repos list

List repos for a classroom assignment. Classroom and assignment arguments use partial name matching.

```
gh-class-sak repos list CLASSROOM ASSIGNMENT [OPTIONS]
```

Options:
- `--repo` — show the full repo name (owner/repo)
- `--name` — show member profile names
- `--group CATEGORY` — match repos to Canvas group categories by fuzzy-matching member names
- `--show-empty` — include teams with no members (hidden by default)

Examples:

```bash
# basic listing
gh-class-sak repos list 195A Group

# with full repo names and member names
gh-class-sak repos list 195A Group --repo --name

# match Canvas project groups
gh-class-sak repos list 195A Group --group Project
```

### repos missing

List students or Canvas groups that don't have a repo for the assignment.

```
gh-class-sak repos missing CLASSROOM ASSIGNMENT [OPTIONS]
```

Options:
- `--group CATEGORY` — show Canvas groups with no matching repo, along with member names

Examples:

```bash
# students without repos
gh-class-sak repos missing 195A Group

# canvas groups without repos
gh-class-sak repos missing 195A Group --group Project
```

## How group matching works

When `--group` is used, the tool:

1. Fetches Canvas groups and their members from the configured course
2. Fetches GitHub repo collaborator profile names
3. Fuzzy-matches names between Canvas and GitHub (handles "Last, First" format, uses similarity threshold)
4. Assigns groups globally so each Canvas group maps to at most one repo
