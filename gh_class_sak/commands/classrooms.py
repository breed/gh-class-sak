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
from gh_class_sak.meta_store import load_meta_classrooms


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
        # an org can host several classrooms, one directory each in its meta
        # repo. without a meta repo the org itself is the classroom and its
        # assignments are inferred from repo names.
        meta_classrooms = load_meta_classrooms(gh, org, get_token())
        if meta_classrooms:
            for classroom_dir, data in sorted(meta_classrooms.items()):
                if data["assignments"]:
                    for assignment in data["assignments"]:
                        output(f"{classroom_dir}: {assignment}")
                else:
                    output(f"{classroom_dir}: (no assignments)")
            continue
        repos = list_org_repos(gh, org)
        prefixes = infer_assignment_prefixes([r.name for r in repos])
        if not prefixes:
            output(f"{org}: (no assignments)")
        else:
            for prefix, _count in prefixes:
                output(f"{org}: {prefix}")
