import sys

import click

from gh_class_sak.core import (
    config_ini,
    configured_orgs,
    error,
    get_github,
    get_token,
    gh_class_sak,
    info,
    output,
    resolve_classroom,
)
from gh_class_sak.github_api import infer_assignment_prefixes, list_org_repos
from gh_class_sak.meta_store import load_meta_courses


@gh_class_sak.command()
@click.argument("classroom", required=False)
def classrooms(classroom):
    """List assignments for CLASSROOM, or for every configured classroom."""
    gh = get_github()

    if classroom:
        org, _partial = resolve_classroom(classroom)
        orgs = [org]
    else:
        # orgs are never discovered from the token: enumerating every org the
        # user belongs to means paginating giant unrelated orgs (e.g. apache)
        orgs = configured_orgs()
        if not orgs:
            error("no classroom given and no configured courses found")
            error(f"pass a classroom (github org), or map courses to orgs in "
                  f"the [COURSES] section of {config_ini}")
            sys.exit(2)

    for org in orgs:
        info(f"scanning {org} ...")
        # the meta repo records the real prefixes; fall back to inference
        meta_courses = load_meta_courses(gh, org, get_token())
        prefixes = [data["prefix"] for _course, data in sorted(meta_courses.items())
                    if data.get("prefix")]
        if not prefixes:
            repos = list_org_repos(gh, org)
            prefixes = [p for p, _count in
                        infer_assignment_prefixes([r.name for r in repos])]
        if not prefixes:
            output(f"{org}: (no assignments)")
        else:
            for prefix in prefixes:
                output(f"{org}: {prefix}")
