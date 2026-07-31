import os
import subprocess
import sys
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from importlib.metadata import version

import click

config_ini = click.get_app_dir("gh-class-sak.ini")


_token = None


def probe_token():
    """(token, source) without exiting; (None, None) when nothing is found."""
    token = os.environ.get("GH_TOKEN")
    if token:
        return token, "GH_TOKEN environment variable"
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        token = result.stdout.strip()
        if token:
            return token, "gh auth token"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        pass
    return None, None


def get_token():
    global _token
    if _token:
        return _token

    token, _source = probe_token()
    if token:
        _token = token
        return token

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
        _github = Github(auth=Auth.Token(get_token()), per_page=100)
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


def progress(items, label, length=None):
    """iterate items behind a stderr progress bar for slow loops.

    a plain passthrough when stderr is not a terminal, so pipes, the doc
    fences, and the test suite see nothing at all.
    """
    if not _interactive():
        yield from items
        return
    with click.progressbar(items, length=length, label=label,
                           file=sys.stderr, show_pos=True) as bar:
        yield from bar


def _announce_dryrun(ctx, param, value):
    """the first thing a previewing command says is that it is previewing."""
    if value:
        would("dry run: no changes will be made. add --no-dryrun to apply")
    return value


dryrun_option = click.option(
    "--dryrun/--no-dryrun", default=True, callback=_announce_dryrun,
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

    a missing file is normal (the config is optional). a file that exists but
    doesn't parse or contains none of the known sections is a mistake, so it
    is at least warned about rather than silently treated as absent.
    """
    if not os.path.exists(config_ini):
        if not required:
            return None
        error(f"config file not found: {config_ini}")
        error("create it with an [ORGS] section (one github org per line)"
              " and, for the canvas features, a [CANVAS] section")
        sys.exit(1)
    # interpolation off: canvas tokens can contain %
    config = ConfigParser(allow_no_value=True, interpolation=None)
    config.optionxform = str  # preserve key case
    try:
        config.read(config_ini)
    except ConfigParserError as exc:
        if not required:
            warn(f"ignoring config {config_ini}: {exc}")
            return None
        error(f"cannot parse {config_ini}: {exc}")
        sys.exit(1)
    if not any(section in config for section in ("CANVAS", "ORGS")):
        if not required:
            warn(f"ignoring config {config_ini}: no [CANVAS] or [ORGS] section")
            return None
        error(f"no [CANVAS] or [ORGS] section in {config_ini}")
        sys.exit(1)
    return config


def get_config():
    return load_config(required=True)


def has_canvas_config():
    """whether the canvas features can work: a config with a [CANVAS] section."""
    config = load_config(required=False)
    return config is not None and "CANVAS" in config


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
    """the GitHub orgs listed in the [ORGS] section, one per line, in order."""
    if config is None:
        config = load_config(required=False)
    if config is None or "ORGS" not in config:
        return []
    seen = set()
    orgs = []
    for org in config.options("ORGS"):
        if org not in seen:
            seen.add(org)
            orgs.append(org)
    return orgs


def add_org_to_config(org):
    """append an org to the [ORGS] section, creating file or section as needed.

    a text-level edit rather than ConfigParser.write, so comments and layout
    in a hand-maintained config survive.
    """
    text = ""
    if os.path.exists(config_ini):
        with open(config_ini) as f:
            text = f.read()
    lines = text.splitlines()
    # configparser accepts trailing text after the ] ("[ORGS]  # my orgs"),
    # so the header match must too, or we append a duplicate section
    header = next((i for i, line in enumerate(lines)
                   if line.strip().startswith("[ORGS]")), None)
    if header is not None:
        lines.insert(header + 1, org)
        text = "\n".join(lines) + "\n"
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        if text:
            text += "\n"
        text += f"[ORGS]\n{org}\n"
    parent = os.path.dirname(config_ini)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config_ini, "w") as f:
        f.write(text)


def match_org(name, orgs):
    """the configured org a partial name means, or None when nothing matches.

    an exact (case-insensitive) match beats partial overlaps; several partial
    matches with no exact winner are an error.
    """
    matched = [org for org in orgs if _names_overlap(name, org)]
    if len(matched) > 1:
        exact = [org for org in matched if org.lower() == name.lower()]
        if len(exact) != 1:
            error(f'"{name}" matches several orgs in {config_ini}:')
            for org in matched:
                error(f"    {org}")
            sys.exit(2)
        matched = exact
    return matched[0] if matched else None


def resolve_classroom(gh, name):
    """resolve a classroom argument to (github org, classroom dir or None).

    the argument names either a configured org or a classroom — a directory
    in one of the configured orgs' classroom-meta repos, so the canvas course
    name works too. an org match wins without touching any meta repo; the
    classroom dir comes back None then, to be pinned later when needed. with
    no configured orgs the argument is used verbatim as an org name.
    """
    orgs = configured_orgs()
    if not orgs:
        return name, None

    org = match_org(name, orgs)
    if org is not None:
        return org, None

    from gh_class_sak.meta_store import load_meta_classrooms

    candidates = []
    for org in orgs:
        for classroom_dir in load_meta_classrooms(gh, org, get_token()):
            if _names_overlap(name, classroom_dir):
                candidates.append((org, classroom_dir))
    if len(candidates) > 1:
        error(f'ambiguous classroom "{name}", matches several classrooms:')
        for org, classroom_dir in candidates:
            error(f"    {org}: {classroom_dir}")
        sys.exit(2)
    if candidates:
        return candidates[0]
    return name, None


def _interactive():
    """warnings are for humans at a terminal, not for pipes or the test suite."""
    return sys.stderr.isatty()


@click.group()
@click.version_option(version=version("gh-class-sak"), prog_name="gh-class-sak")
def gh_class_sak():
    if not _interactive():
        return
    warn("this is beta code to replace github classroom, which is going away")
    if not configured_orgs():
        warn("unlike the pre-1.0 versions, this program replaces github classroom"
             " rather than working with it — run: gh-class-sak help-me-setup")
