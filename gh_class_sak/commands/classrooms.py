from gh_class_sak.core import (
    configured_orgs,
    error,
    get_github,
    get_token,
    gh_class_sak,
    output,
)
from gh_class_sak.github_api import infer_assignment_prefixes, list_org_repos
from gh_class_sak.meta_store import load_meta_classrooms


@gh_class_sak.command()
def classrooms():
    """List classrooms and their assignments."""
    gh = get_github()

    orgs = configured_orgs()
    if not orgs:
        # no config: fall back to every org the token can see
        orgs = [o.login for o in gh.get_user().get_orgs()]

    if not orgs:
        error("no classrooms found")
        error("add orgs to the [COURSES] section of the config, or join an org")
        return

    for org in orgs:
        # an org can host several classrooms, one directory each in its meta
        # repo. without a meta repo the org itself is the classroom and its
        # assignments are inferred from repo names.
        meta_classrooms = load_meta_classrooms(gh, org, get_token())
        if meta_classrooms:
            for classroom_dir, data in sorted(meta_classrooms.items()):
                if data.get("prefix"):
                    output(f"{classroom_dir}: {data['prefix']}")
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
