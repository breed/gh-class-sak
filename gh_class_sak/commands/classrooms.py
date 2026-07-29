from gh_class_sak.core import (
    configured_orgs,
    error,
    get_github,
    get_token,
    gh_class_sak,
    output,
)
from gh_class_sak.github_api import infer_assignment_prefixes, list_org_repos
from gh_class_sak.meta_store import load_meta_courses


@gh_class_sak.command()
def classrooms():
    """List classrooms (GitHub orgs) and their assignments."""
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
