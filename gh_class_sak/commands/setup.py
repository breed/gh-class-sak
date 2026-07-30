"""help-me-setup: explain the config file and verify the whole setup.

read-only: it changes nothing, so it takes no --dryrun flag. exit 0 when
everything checks out, 1 when something needs attention. every finding of
something missing comes with an example of what the fix looks like.
"""

import sys

from github import GithubException

from gh_class_sak.canvas_api import get_canvas as canvas_client
from gh_class_sak.canvas_api import list_courses
from gh_class_sak.core import (
    config_ini,
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


def _example(lines, lead="for example:"):
    output("")
    output(f"  {lead}")
    for line in lines:
        output(f"      {line}")
    output("")


@gh_class_sak.command("help-me-setup")
def help_me_setup():
    """Explain the config file and check that everything is set up."""
    problems = []

    token, source = probe_token()
    if token:
        output(f"github token   found ({source})")
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
        warn(f"config file    none at {config_ini}")
        _example(CONFIG_TEMPLATE, lead="create it with content like:")
        output("[ORGS] lists the github orgs hosting your classrooms — it lets you")
        output("name a classroom by its course name, and `classrooms` with no")
        output("argument lists every org there. [CANVAS] is optional; it unlocks")
        output("the roster features (--group, --instructors, --email, repos")
        output("missing) and resolving student emails to github accounts.")
    else:
        output(f"config file    {config_ini}")

        orgs = configured_orgs(config)
        if not orgs:
            problems.append("[ORGS]")
            warn("[ORGS]         no orgs listed — add one github org per line")
            _example(ORGS_EXAMPLE)
        else:
            output(f"[ORGS]         {', '.join(orgs)}")
            if token:
                from gh_class_sak.meta_store import load_meta_classrooms
                gh = get_github()
                for org in orgs:
                    try:
                        gh.get_organization(org)
                    except GithubException:
                        problems.append(org)
                        error(f"  {org}: not reachable with this token —"
                              " check the spelling and the token's org access")
                        continue
                    meta_classrooms = load_meta_classrooms(gh, org, get_token())
                    if meta_classrooms:
                        output(f"  {org}: classroom-meta ok —"
                               f" {', '.join(sorted(meta_classrooms))}")
                    else:
                        problems.append(f"{org} classroom-meta")
                        warn(f"  {org}: no classroom-meta repo")
                        _example([f"gh-class-sak meta init YOUR-COURSE --org {org}",
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
