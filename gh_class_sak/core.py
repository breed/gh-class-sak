import os
import subprocess
import sys
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from importlib.metadata import version

import click

config_ini = click.get_app_dir("gh-class-sak.ini")


def get_token():
    token = os.environ.get("GH_TOKEN")
    if token:
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
        token = result.stdout.strip()
        if token:
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    error("no github token found. either:")
    error("  - set GH_TOKEN environment variable")
    error("  - install gh CLI and run: gh auth login")
    sys.exit(1)


_github = None


def get_github():
    """Return a cached PyGithub client authenticated with the resolved token."""
    global _github
    if _github is None:
        from github import Auth, Github
        _github = Github(auth=Auth.Token(get_token()))
    return _github


def error(message):
    click.echo(click.style(message, fg='red'), err=True)


def info(message):
    click.echo(click.style(message, fg='blue'), err=True)


def warn(message):
    click.echo(click.style(message, fg='yellow'), err=True)


def output(message):
    click.echo(message)


def would(message):
    """print what a mutating command would do, per the --dryrun convention."""
    output(f"\N{WARNING SIGN}\N{VARIATION SELECTOR-16}  {message}")


dryrun_option = click.option(
    "--dryrun/--no-dryrun", default=True,
    help="preview changes (default); --no-dryrun applies them",
)


def _get_name(item):
    """get name from a dict or canvasapi object."""
    if isinstance(item, dict):
        return item.get("name", "")
    return getattr(item, "name", "")


def resolve_name(items, name, label):
    """find one item by partial name match, error on 0 or ambiguous matches."""
    matches = [i for i in items if name.lower() in _get_name(i).lower()]
    if len(matches) == 0:
        error(f'no {label} found matching "{name}". options are:')
        for i in items:
            error(f"    {_get_name(i)}")
        sys.exit(2)
    if len(matches) > 1:
        # check for exact match
        exact = [i for i in matches if _get_name(i).lower() == name.lower()]
        if len(exact) == 1:
            return exact[0]
        error(f'multiple {label}s found matching "{name}":')
        for i in matches:
            error(f"    {_get_name(i)}")
        sys.exit(2)
    return matches[0]


def normalize_course_name(name):
    return name.replace(":", "").replace(" ", "_").replace("-", "_").lower()


def load_config(required=True):
    """read the ini config; return None instead of exiting when not required.

    a missing file is normal (the canvas features are optional). a file that
    exists but doesn't parse or lacks a section is a mistake, so it is at
    least warned about rather than silently treated as absent.
    """
    if not os.path.exists(config_ini):
        if not required:
            return None
        error(f"config file not found: {config_ini}")
        error("create it with [CANVAS] and [COURSES] sections")
        sys.exit(1)
    config = ConfigParser()
    config.optionxform = str  # preserve key case
    try:
        config.read(config_ini)
    except ConfigParserError as exc:
        if not required:
            warn(f"ignoring config {config_ini}: {exc}")
            return None
        error(f"cannot parse {config_ini}: {exc}")
        sys.exit(1)
    for section in ("CANVAS", "COURSES"):
        if section not in config:
            if not required:
                warn(f"ignoring config {config_ini}: missing [{section}] section")
                return None
            error(f"missing [{section}] section in {config_ini}")
            sys.exit(1)
    return config


def get_config():
    return load_config(required=True)


def get_canvas():
    from gh_class_sak.canvas_api import get_canvas as _get_canvas
    config = get_config()
    try:
        return _get_canvas(config)
    except ValueError as e:
        error(str(e))
        sys.exit(1)


def _names_overlap(a, b):
    """bidirectional substring match on normalized course/org names."""
    na = normalize_course_name(a)
    nb = normalize_course_name(b)
    return na in nb or nb in na


def configured_orgs(config=None):
    """the GitHub orgs listed as [COURSES] values, in config order."""
    if config is None:
        config = load_config(required=False)
    if config is None:
        return []
    seen = set()
    orgs = []
    for _, org in config.items("COURSES"):
        if org not in seen:
            seen.add(org)
            orgs.append(org)
    return orgs


def resolve_classroom(name):
    """resolve a partial classroom name to (github org, canvas course partial).

    matches either side of a [COURSES] mapping, so both the canvas course
    partial and the org name work. several courses may share one org, in which
    case naming the org alone leaves the canvas partial undetermined and it
    comes back None. falls back to treating the argument as a literal org name,
    so the tool works with no config at all.
    """
    config = load_config(required=False)
    if config is None:
        return name, None

    entries = [(canvas_partial, org) for canvas_partial, org in config.items("COURSES")
               if _names_overlap(name, org) or _names_overlap(name, canvas_partial)]
    if not entries:
        return name, None

    orgs = []
    for _, org in entries:
        if org not in orgs:
            orgs.append(org)
    if len(orgs) > 1:
        exact = [org for org in orgs if org.lower() == name.lower()]
        if len(exact) != 1:
            error(f'ambiguous classroom "{name}", matches several orgs in {config_ini}:')
            for org in orgs:
                error(f"    {org}")
            sys.exit(2)
        orgs = exact

    org = orgs[0]
    partials = [c for c, o in entries if o == org]
    return org, partials[0] if len(partials) == 1 else None


def resolve_org(name):
    """resolve a partial classroom name to a GitHub org."""
    return resolve_classroom(name)[0]


def resolve_course_mapping(config, org):
    """map a resolved GitHub org back to its Canvas course partial."""
    matches = []
    for canvas_partial, github_org in config.items("COURSES"):
        if _names_overlap(org, github_org):
            matches.append((canvas_partial, github_org))
    if len(matches) == 0:
        error(f'no course mapping found for org "{org}" in {config_ini}')
        error("configured mappings:")
        for k, v in config.items("COURSES"):
            error(f"    {k} = {v}")
        sys.exit(2)
    if len(matches) > 1:
        error(f'"{org}" hosts several canvas courses, so the course is ambiguous:')
        for k, v in matches:
            error(f"    {k} = {v}")
        error("name one of the courses instead of the org")
        sys.exit(2)
    return matches[0][0]


@click.group()
@click.version_option(version=version("gh-class-sak"), prog_name="gh-class-sak")
def gh_class_sak():
    pass
