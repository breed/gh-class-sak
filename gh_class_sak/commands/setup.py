"""help-me-setup: explain the config file and verify the whole setup.

read-only unless asked: only --create-config (or a yes at the terminal's
offer) writes, and then only the config file — missing sections are added,
nothing is ever overwritten. so it takes no --dryrun flag. exit 0 when
everything checks out, 1 when something needs attention. every finding of
something missing comes with an example of what the fix looks like.
"""

import sys

import click
from github import GithubException

from gh_class_sak.canvas_api import get_canvas as canvas_client
from gh_class_sak.canvas_api import list_courses
from gh_class_sak import core
from gh_class_sak.core import (
    add_canvas_to_config,
    add_org_to_config,
    configured_orgs,
    error,
    get_github,
    get_token,
    gh_class_sak,
    load_config,
    output,
    probe_token,
    warn,
)
from gh_class_sak.github_api import token_login

ORGS_EXAMPLE = (
    "[ORGS]",
    "# one github org per line",
    "your-github-org",
)
CANVAS_EXAMPLE = (
    "[CANVAS]",
    "url = https://your-canvas-instance.instructure.com",
    "token = YOUR_CANVAS_API_TOKEN",
)
CONFIG_TEMPLATE = ORGS_EXAMPLE + ("",) + CANVAS_EXAMPLE


def _can_ask():
    """questions only when a person is typing: never in a pipe or a test."""
    return sys.stdin.isatty()


def _create_config(config):
    """ask for whatever sections the config lacks and append them."""
    has_orgs = config is not None and configured_orgs(config)
    has_canvas = config is not None and "CANVAS" in config
    if has_orgs and has_canvas:
        output(f"{core.config_ini} already has [ORGS] and [CANVAS]; nothing to add")
        return
    if not has_orgs:
        org = click.prompt("github org hosting your courses").strip()
        add_org_to_config(org)
    if not has_canvas:
        url = click.prompt("canvas url, e.g. https://school.instructure.com"
                           " (blank to skip canvas)", default="",
                           show_default=False).strip()
        if url:
            token = click.prompt("canvas api token (Account > Settings >"
                                 " New Access Token)", hide_input=True).strip()
            add_canvas_to_config(url, token)
    output(f"wrote {core.config_ini}")
    output("")


def _check_token_scope(problems):
    """a classic token without the repo scope can't see private repos — and
    classroom-meta is private. say so up front, with the one-line fix."""
    gh = get_github()
    login = token_login(gh)
    scopes = getattr(gh, "oauth_scopes", None)
    if scopes is not None and "repo" not in scopes:
        problems.append("token scope")
        who = f' ("{login}")' if login else ""
        warn(f'token scope    the token{who} lacks the "repo" scope, so private'
             " repos like classroom-meta are invisible to it")
        _example(["gh auth refresh -h github.com -s repo"], lead="fix it with:")


def _example(lines, lead="for example:"):
    output("")
    output(f"  {lead}")
    for line in lines:
        output(f"      {line}")
    output("")


@gh_class_sak.command("help-me-setup")
@click.option("--create-config", is_flag=True,
              help="ask for the org and canvas details and write the config"
                   " file (only missing sections are added)")
def help_me_setup(create_config):
    """Explain the config file and check that everything is set up.

    With --create-config it first asks for whatever the config file is
    missing and writes it; nothing already there is changed.

    \b
    Examples:
      gh-class-sak help-me-setup
      gh-class-sak help-me-setup --create-config
    """
    problems = []

    config = load_config(required=False)
    if create_config or (config is None and _can_ask() and click.confirm(
            f"no config file at {core.config_ini}. create it now?", default=True)):
        _create_config(config)

    token, source = probe_token()
    if token:
        output(f"github token   found ({source})")
        _check_token_scope(problems)
    else:
        problems.append("github token")
        error("github token   not found. either:")
        error("  - set the GH_TOKEN environment variable")
        error("  - install the gh CLI and run: gh auth login")
        _example(["export GH_TOKEN=ghp_yourtokenhere",
                  "# or, once the gh CLI is logged in, nothing at all"])

    config = load_config(required=False)
    if config is None:
        problems.append("config file")
        warn(f"config file    none at {core.config_ini}")
        _example(CONFIG_TEMPLATE, lead="create it with content like:")
        output("or let this tool write it: gh-class-sak help-me-setup --create-config")
        output("[ORGS] lists the github orgs hosting your courses — commands then")
        output("find a course by its name, and `course list` with no argument")
        output("lists every course in them. [CANVAS] is optional; it unlocks")
        output("the roster features (--group, --instructors, --email, repos")
        output("missing) and resolving student emails to github accounts.")
    else:
        output(f"config file    {core.config_ini}")

        orgs = configured_orgs(config)
        if not orgs:
            problems.append("[ORGS]")
            warn("[ORGS]         no orgs listed — add one github org per line")
            _example(ORGS_EXAMPLE)
        else:
            output(f"[ORGS]         {', '.join(orgs)}")
            if token:
                from gh_class_sak.meta_store import (
                    read_meta_classrooms,
                    report_missing_meta,
                )
                gh = get_github()
                for org in orgs:
                    try:
                        gh.get_organization(org)
                    except GithubException:
                        problems.append(org)
                        error(f"  {org}: not reachable with this token —"
                              " check the spelling and the token's org access")
                        continue
                    meta_classrooms, why = read_meta_classrooms(
                        gh, org, get_token())
                    if meta_classrooms:
                        output(f"  {org}: classroom-meta ok —"
                               f" {', '.join(sorted(meta_classrooms))}")
                    else:
                        problems.append(f"{org} classroom-meta")
                        report_missing_meta(gh, org, why, report=warn,
                                            prefix="  ")
                        if why != "unreadable":
                            # a repo that is there but unreadable is a
                            # checkout to fix, not a course to create
                            _example([f"gh-class-sak course init YOUR-COURSE --org {org}",
                                      "# or import a GitHub Classroom era org wholesale:",
                                      f"gh-class-sak migrate-github-classroom {org}"],
                                     lead="create one with:")
            else:
                warn("  (orgs not checked — no github token)")

        if "CANVAS" in config:
            try:
                courses = list_courses(canvas_client(config))
            except ValueError as exc:
                problems.append("[CANVAS]")
                error(f"[CANVAS]       {exc}")
                _example(CANVAS_EXAMPLE, lead="the section should look like:")
            except Exception as exc:
                problems.append("[CANVAS]")
                error(f"[CANVAS]       cannot reach canvas: {exc}")
            else:
                names = ", ".join(c.name for c in courses[:5])
                output(f"[CANVAS]       ok — teaching: {names or '(no courses visible)'}")
        else:
            output("[CANVAS]       not configured (optional — canvas features disabled)")
            _example(CANVAS_EXAMPLE, lead="to enable the roster features, add:")

    output("")
    if problems:
        error(f"needs attention: {', '.join(problems)}")
        sys.exit(1)
    output("everything looks good")
