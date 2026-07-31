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
from gh_class_sak.meta_store import load_meta_classrooms


@gh_class_sak.command()
@click.argument("classroom", required=False)
def classrooms(classroom):
    """List assignments for CLASSROOM, or for every configured classroom."""
    gh = get_github()

    partial = None
    if classroom:
        org, partial = resolve_classroom(gh, classroom)
        orgs = [org]
    else:
        # orgs are never discovered from the token: enumerating every org the
        # user belongs to means paginating giant unrelated orgs (e.g. apache)
        orgs = configured_orgs()
        if not orgs:
            error("no classroom given and no configured orgs found")
            error(f"pass a classroom (github org), or list orgs in "
                  f"the [ORGS] section of {config_ini}")
            sys.exit(2)

    missing = False
    for org in orgs:
        info(f"scanning {org} ...")
        # an org hosts a set of classrooms, one directory each in its
        # classroom-meta repo
        meta_classrooms = load_meta_classrooms(gh, org, get_token())
        if not meta_classrooms:
            error(f'no classroom-meta repo in "{org}". create one with: meta init')
            missing = True
            continue
        if partial:
            # the argument named one classroom, not its whole host org
            meta_classrooms = {name: data
                               for name, data in meta_classrooms.items()
                               if name == partial}
        for classroom_dir, data in sorted(meta_classrooms.items()):
            if data["assignments"]:
                for assignment in data["assignments"]:
                    output(f"{classroom_dir}: {assignment}")
            else:
                output(f"{classroom_dir}: (no assignments)")
    if missing:
        sys.exit(2)
