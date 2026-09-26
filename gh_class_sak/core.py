import os
import shutil
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


class _BarHold:
    """messages arriving while a progress bar owns the terminal line.

    each one is flashed at the end of the bar's line, staying up until the
    next message replaces it, and all of them are replayed for real —
    colors, streams, and order intact — once the bar finishes.
    """

    def __init__(self, label):
        self.label = label
        self.bar = None
        self.held = []  # (message, fg, err) in arrival order
        self.flash = ""

    def show(self, _item=None):
        """item_show_func for the bar: the latest message, on its line."""
        return self.flash or None

    def add(self, message, fg, err):
        self.held.append((message, fg, err))
        # the flash must stay on the bar's single line, or the \r redraw
        # leaves wrapped leftovers behind: first line only, clipped to fit
        first = message.splitlines()[0] if message else ""
        self.flash = ""
        base = len(self.label) + 50
        if self.bar is not None:
            try:
                # the bar line as it stands without a flash, measured exactly
                base = len(self.bar.format_progress_line())
            except AttributeError:
                pass
        avail = shutil.get_terminal_size().columns - base - 3
        if avail >= 8:
            self.flash = first if len(first) <= avail \
                else first[:avail - 1] + "\N{HORIZONTAL ELLIPSIS}"
        if self.bar is not None:
            self.bar.render_progress()

    def replay(self):
        # through _echo, so a nested bar's messages hand off to the outer one
        for message, fg, err in self.held:
            _echo(message, fg=fg, err=err)


_bar_holds = []  # innermost active progress bar last


def _echo(message, fg=None, err=False):
    """the one exit for messages: straight through, unless a progress bar
    owns the line — then held for the bar to flash now and replay at its end."""
    if _bar_holds:
        _bar_holds[-1].add(message, fg, err)
        return
    click.echo(click.style(message, fg=fg) if fg else message, err=err)


# what the running command has said so far: the dry-run footer and the
# end-of-run summaries read it. reset at the start of every invocation
said = {"would": 0, "warn": 0, "error": 0}

# ctx.meta key set by the renamed (pre-course) commands: their output stays
# exactly as it was, so no footer, summary, or next-step hint
LEGACY = "gh_class_sak.legacy"


def error(message):
    said["error"] += 1
    _echo(message, fg="red", err=True)


def info(message):
    _echo(message, fg="blue", err=True)


def warn(message):
    said["warn"] += 1
    _echo(message, fg="yellow", err=True)


def output(message):
    _echo(message)


def _warning_line(message):
    output(f"\N{WARNING SIGN}\N{VARIATION SELECTOR-16}  {message}")


def would(message):
    """print what a mutating command would do, per the --dryrun convention."""
    said["would"] += 1
    _warning_line(message)


def is_legacy():
    """whether a renamed command is running, whose output must not change."""
    ctx = click.get_current_context(silent=True)
    return bool(ctx and ctx.meta.get(LEGACY))


def progress(items, label, length=None):
    """iterate items behind a stderr progress bar for slow loops.

    a plain passthrough when stderr is not a terminal, so pipes, the doc
    fences, and the test suite see nothing at all. a message printed while
    the bar is up is flashed at the end of the bar's line — staying there
    until the next message replaces it — and every held message prints for
    real when the bar finishes.
    """
    if not _interactive():
        yield from items
        return
    hold = _BarHold(label)
    try:
        with click.progressbar(items, length=length, label=label,
                               file=sys.stderr, show_pos=True,
                               item_show_func=hold.show) as bar:
            hold.bar = bar
            _bar_holds.append(hold)
            yield from bar
    finally:
        if hold in _bar_holds:
            _bar_holds.remove(hold)
        hold.replay()


def _announce_dryrun(ctx, param, value):
    """the first thing a previewing command says is that it is previewing —
    and, when it previewed anything, the last thing too, since a long
    preview scrolls the first line away."""
    if value:
        if ctx.meta.get(LEGACY):
            _warning_line("dry run: no changes will be made. add --no-dryrun to apply")
        else:
            _warning_line("dry run: no changes will be made. add --apply to make them")
        ctx.call_on_close(lambda: _dryrun_footer(ctx))
    return value


def announce_dryrun():
    """the dryrun option's announcement, for a command that previews only
    some of the time (a settings command that shows when given nothing)."""
    ctx = click.get_current_context()
    _announce_dryrun(ctx, None, True)


def _dryrun_footer(ctx):
    if said["would"] and not ctx.meta.get(LEGACY):
        _warning_line("that was a preview: nothing changed. add --apply to make"
                      " these changes")


# --apply is the plain-words spelling of --no-dryrun; both work
DRYRUN_FLAGS = ("--dryrun/--no-dryrun", " /--apply")
DRYRUN_HELP = "preview changes (default); --apply (or --no-dryrun) makes them"

dryrun_option = click.option(
    *DRYRUN_FLAGS, default=True, callback=_announce_dryrun, help=DRYRUN_HELP,
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
        error(f'ambiguous course "{name}", matches several courses:')
        for org, classroom_dir in candidates:
            error(f"    {org}: {classroom_dir}")
        sys.exit(2)
    if candidates:
        return candidates[0]
    return name, None


def resolve_course(gh, name, org=None):
    """resolve a COURSE argument to (github org, classroom dir).

    unlike resolve_classroom the argument is always a course, never an org:
    it matches the classroom directories of --org, or else of every
    configured org. an exact name beats partial overlaps.
    """
    from gh_class_sak.meta_store import read_meta_classrooms, report_missing_meta

    if org:
        orgs = [match_org(org, configured_orgs()) or org]
    else:
        orgs = configured_orgs()
        if not orgs:
            error(f'which org hosts course "{name}"? pass --org ORG, or list'
                  f" orgs in the [ORGS] section of {config_ini}")
            sys.exit(2)

    candidates = []
    unreadable = []
    for candidate_org in orgs:
        classrooms, why = read_meta_classrooms(gh, candidate_org, get_token())
        if not classrooms:
            unreadable.append((candidate_org, why))
        candidates.extend((candidate_org, classroom_dir)
                          for classroom_dir in classrooms
                          if _names_overlap(name, classroom_dir))
    exact = [c for c in candidates if c[1] == normalize_course_name(name)]
    if len(exact) == 1:
        return exact[0]
    if len(candidates) > 1:
        error(f'ambiguous course "{name}", matches several courses:')
        for candidate_org, classroom_dir in candidates:
            error(f"    {candidate_org}: {classroom_dir}")
        sys.exit(2)
    if candidates:
        return candidates[0]

    for candidate_org, why in unreadable:
        report_missing_meta(gh, candidate_org, why)
    error(f'no course "{name}" recorded in {", ".join(orgs)}.'
          " run: course list")
    if not org and any(_names_overlap(name, o) for o in orgs):
        error(f'"{name}" looks like an org: pass it as --org {name}')
    sys.exit(2)


def _interactive():
    """warnings are for humans at a terminal, not for pipes or the test suite."""
    return sys.stderr.isatty()


def renamed(old, new):
    """point a human at the new name of a renamed command; scripts see nothing."""
    if _interactive():
        warn(f'"{old}" is renamed: use {new}')


class UsageOrderGroup(click.Group):
    """a group whose --help lists its commands in the order they're used —
    setup first — instead of alphabetically. commands the order doesn't
    name follow, alphabetically."""

    def __init__(self, *args, order=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.order = list(order)

    def list_commands(self, ctx):
        names = super().list_commands(ctx)
        return ([name for name in self.order if name in names]
                + [name for name in names if name not in self.order])


@click.group(cls=UsageOrderGroup, order=(
    "help-me-setup", "course", "assignment", "sync", "repos", "canvas",
    "migrate-github-classroom"))
@click.version_option(version=version("gh-class-sak"), prog_name="gh-class-sak")
def gh_class_sak():
    """Manage a course's GitHub repos from the command line.

    \b
    course      one per Canvas course, hosted in a GitHub org
    assignment  one repo per student or group in a course, e.g. hw1 gives
                cs101-hw1-alice, cs101-hw1-bob
    \b
    New here? Run help-me-setup to check your setup, then course init, then
    assignment create, then sync whenever the roster changes.
    """
    for key in said:
        said[key] = 0
    if not _interactive():
        return
    warn("this is beta code to replace github classroom, which is going away")
    if not configured_orgs():
        warn("unlike the pre-1.0 versions, this program replaces github classroom"
             " rather than working with it — run: gh-class-sak help-me-setup")
