import sys

import click

from gh_class_sak import meta_store as ms
from gh_class_sak.commands.repos import Classroom, fetch_enrollment_data, print_table
from gh_class_sak.core import (
    dryrun_option,
    error,
    get_github,
    get_token,
    gh_class_sak,
    load_config,
    normalize_course_name,
    output,
    resolve_classroom,
    warn,
    would,
)
from gh_class_sak.github_api import (
    UNPROTECTED,
    add_collaborator,
    create_org_repo,
    create_team,
    get_org_repo,
    get_repo_by_id,
    get_team,
    infer_assignment_prefixes,
    list_org_repos,
    protect_default_branch,
    read_default_branch_protection,
    remove_collaborator,
    resolve_email_to_username,
    split_collaborators,
)

REPO_SETTING_KEYS = ("protection", "linear_history", "force_push")


def tas_team_name(classroom_dir):
    """each classroom gets its own COURSENAME-tas team, so TAs of one
    classroom in an org don't gain access to another classroom's repos."""
    return f"{classroom_dir}-tas"


def _perform(dryrun, message, fn, actions):
    """the --dryrun convention: preview with ⚠️, or do it and say so."""
    actions.append(message)
    if dryrun:
        would(f"would {message}")
    else:
        fn()
        output(message)


def _open_meta(gh, org, required=True):
    """(meta_repo, checkout_path); errors out when required and absent."""
    repo = get_org_repo(gh, org, ms.META_REPO_NAME)
    if repo is None:
        if required:
            error(f'no meta repo in "{org}". create one with: meta init')
            sys.exit(2)
        return None, None
    try:
        return repo, ms.checkout_meta(repo.clone_url, org, get_token())
    except RuntimeError as exc:
        error(str(exc))
        sys.exit(2)


def _resolve_classroom_dir(checkout, partial, classroom):
    """pick the classroom directory the classroom argument means."""
    candidates = ms.list_classrooms(checkout)
    key = normalize_course_name(partial) if partial else None
    if key:
        if key in candidates:
            return key
        error(f'classroom "{key}" is not in the meta repo. classrooms there:')
        for c in candidates:
            error(f"    {c}")
        error("run: meta init")
        sys.exit(2)
    if len(candidates) == 1:
        return candidates[0]
    key = normalize_course_name(classroom)
    if key in candidates:
        return key
    error(f'cannot tell which classroom "{classroom}" means. classrooms in the meta repo:')
    for c in candidates:
        error(f"    {c}")
    sys.exit(2)


def _load_classroom(checkout, classroom):
    """load_classroom, exiting with the message when classroom.ini is invalid."""
    try:
        return ms.load_classroom(checkout, classroom)
    except ValueError as exc:
        error(f"{classroom}/classroom.ini: {exc}")
        sys.exit(2)


def _ini_settings(data):
    """a classroom's raw repo-setting keys, for passing back through save_classroom."""
    return {key: data[key] for key in REPO_SETTING_KEYS}


def _make_resolver(gh, org, course_partial):
    """entry -> github login. logins pass through; emails resolve via the
    canvas roster (profile links) and then the github search api. returns
    None for an email nothing can resolve."""
    cache = {}
    canvas_map = None

    def _canvas_lookup(email):
        nonlocal canvas_map
        if canvas_map is None:
            canvas_map = {}
            if load_config(required=False) and course_partial:
                data = fetch_enrollment_data(Classroom(org, course_partial),
                                             resolve_students=True)
                for person in data["students"] + data["instructors"]:
                    if person.get("email") and person.get("github"):
                        canvas_map[person["email"].lower()] = person["github"]
        return canvas_map.get(email.lower())

    def resolve(entry):
        if "@" not in entry:
            return entry
        if entry not in cache:
            cache[entry] = _canvas_lookup(entry) or resolve_email_to_username(gh, entry)
        return cache[entry]

    return resolve


def _resolve_row_students(row, resolve):
    """resolved logins for a row; noticeable error per unresolvable email."""
    logins = []
    unresolved = []
    for entry in row["students"]:
        login = resolve(entry)
        if login:
            logins.append(login)
        else:
            error(f'cannot resolve "{entry}" (row {row["name"]}) to a github id')
            unresolved.append(entry)
    return logins, unresolved


def _template_repo(gh, data):
    if not data["template"]:
        return None
    repo = get_org_repo(gh, *data["template"].split("/", 1)) \
        if "/" in data["template"] else None
    if repo is None:
        error(f'template repo "{data["template"]}" not found (need OWNER/NAME)')
        sys.exit(2)
    return repo


def _protection_summary(desired):
    """the settings trio as prose for action messages."""
    protection, linear_history, force_push = desired
    parts = []
    if protection == "pr-review":
        parts.append("require pr review")
    if linear_history:
        parts.append("linear history")
    if not force_push:
        parts.append("no force push")
    return ", ".join(parts)


def _reconcile_repo_protection(repo, desired, dryrun, actions):
    """put the classroom's branch protection on a repo when it has drifted.

    desired == UNPROTECTED enforces nothing, so nothing is written — existing
    protection is left alone rather than deleted.
    """
    if desired == UNPROTECTED:
        return
    current = read_default_branch_protection(repo)
    if current is None or current == desired:
        return

    def _protect():
        protect_default_branch(repo, *desired)
    _perform(dryrun, f"protect {repo.default_branch} on {repo.full_name}"
             f" ({_protection_summary(desired)})", _protect, actions)


def _realize_classroom(gh, org, data, resolve, dryrun, actions):
    """create/adopt the repo for every row that has none, and grant push.

    mutates rows in place under --no-dryrun. returns (changed, unresolved).
    """
    prefix = data["prefix"]
    template = _template_repo(gh, data)
    desired = ms.effective_repo_settings(data)
    changed = False
    all_unresolved = []
    for row in data["rows"]:
        if row["repo_id"] is not None:
            continue
        logins, unresolved = _resolve_row_students(row, resolve)
        all_unresolved.extend(unresolved)
        repo_name = f"{prefix}-{row['name']}"
        existing = get_org_repo(gh, org, repo_name)

        made = {}
        if existing is not None:
            def _adopt(existing=existing, made=made):
                made["repo"] = existing
            _perform(dryrun, f"adopt existing {existing.full_name} for {row['name']}",
                     _adopt, actions)
            _reconcile_repo_protection(existing, desired, dryrun, actions)
        else:
            source = f" from {template.full_name}" if template else ""
            def _create(repo_name=repo_name, made=made):
                made["repo"] = create_org_repo(gh, org, repo_name, template=template)
            _perform(dryrun, f"create private {org}/{repo_name}{source}", _create, actions)
            if desired != UNPROTECTED:
                if template is not None:
                    def _protect(made=made):
                        protect_default_branch(made["repo"], *desired)
                    _perform(dryrun, f"protect default branch on {org}/{repo_name}"
                             f" ({_protection_summary(desired)})", _protect, actions)
                else:
                    warn(f"{org}/{repo_name} starts with no branch;"
                         " run meta apply after the first push to protect it")

        for login in logins:
            def _grant(login=login, made=made):
                add_collaborator(made["repo"], login, "push")
            _perform(dryrun, f"grant push to {login} on {org}/{repo_name}",
                     _grant, actions)

        if not dryrun:
            row["repo"] = made["repo"].html_url
            row["repo_id"] = made["repo"].id
            changed = True
    return changed, all_unresolved


def _reconcile_row_collaborators(gh, repo, logins, dryrun, actions):
    """make the repo's non-admin collaborators exactly the row's students."""
    members, _admins = split_collaborators(repo)
    desired = {login.lower(): login for login in logins}
    current = {m.login.lower(): m.login for m in members}
    for lowered, login in desired.items():
        if lowered not in current:
            def _grant(login=login):
                add_collaborator(repo, login, "push")
            _perform(dryrun, f"grant push to {login} on {repo.full_name}",
                     _grant, actions)
    for lowered, login in current.items():
        if lowered not in desired:
            def _revoke(login=login):
                remove_collaborator(repo, login)
            _perform(dryrun, f"revoke {login} from {repo.full_name}", _revoke, actions)


@gh_class_sak.group()
def meta():
    """Manage the org's meta repo: one directory per classroom."""
    pass


@meta.command("init")
@click.argument("classroom")
@click.option("--prefix", default=None,
              help="the classroom repo prefix (default: inferred when unambiguous)")
@click.option("--template", default=None,
              help="OWNER/NAME template repo for created assignment repos")
@dryrun_option
def meta_init(classroom, prefix, template, dryrun):
    """Create the meta repo and scaffold a classroom in it."""
    gh = get_github()
    org, partial = resolve_classroom(classroom)
    classroom_dir = normalize_course_name(partial or classroom)

    meta_repo, checkout = _open_meta(gh, org, required=False)
    existing = _load_classroom(checkout, classroom_dir) if checkout else None

    if prefix is None:
        prefix = existing["prefix"] if existing else None
    if prefix is None:
        inferred = infer_assignment_prefixes([r.name for r in list_org_repos(gh, org)])
        if len(inferred) == 1:
            prefix = inferred[0][0]
        else:
            error("--prefix is required; inferred candidates:")
            for p, count in inferred:
                error(f"    {p} ({count} repos)")
            sys.exit(2)
    if template is None and existing:
        template = existing["template"]

    tas = list(existing["tas"]) if existing else []
    if load_config(required=False):
        data = fetch_enrollment_data(Classroom(org, partial or classroom_dir))
        for inst in data["instructors"]:
            entry = inst.get("github") or inst.get("email")
            if entry and entry not in tas:
                tas.append(entry)
    elif not tas:
        warn("no canvas config; seed the tas file by hand")

    actions = []
    if meta_repo is None:
        def _create_meta():
            repo = create_org_repo(gh, org, ms.META_REPO_NAME, auto_init=True)
            ms.checkout_meta(repo.clone_url, org, get_token())
        _perform(dryrun, f"create private {org}/{ms.META_REPO_NAME}", _create_meta, actions)

    settings = _ini_settings(existing) if existing else {}

    def _write():
        checkout_now = ms.meta_checkout_dir(org)
        rows = existing["rows"] if existing else []
        ms.save_classroom(checkout_now, classroom_dir, prefix, template,
                          tas=tas, rows=rows, **settings)
        ms.commit_and_push(checkout_now, f"init {classroom_dir}", get_token())
    _perform(dryrun,
             f"record {classroom_dir}: prefix={prefix}"
             + (f" template={template}" if template else "")
             + f" tas={','.join(tas) or '-'}",
             _write, actions)


@meta.command("show")
@click.argument("classroom")
def meta_show(classroom):
    """Show a classroom's recorded state."""
    gh = get_github()
    org, partial = resolve_classroom(classroom)
    _repo, checkout = _open_meta(gh, org)
    classroom_dir = _resolve_classroom_dir(checkout, partial, classroom)
    data = _load_classroom(checkout, classroom_dir)

    protection, linear_history, force_push = ms.effective_repo_settings(data)
    output(f"CLASSROOM {classroom_dir}")
    output(f"PREFIX    {data['prefix']}")
    if data["template"]:
        output(f"TEMPLATE  {data['template']}")
    output(f"TAS       {','.join(data['tas']) or '-'}")
    output(f"SETTINGS  protection={protection}"
           f" linear_history={str(linear_history).lower()}"
           f" force_push={str(force_push).lower()}")
    output("")
    print_table(list(ms.STUDENTS_HEADERS),
                [[row["name"],
                  ",".join(row["students"]) or ms.EMPTY,
                  row["repo"] or ms.EMPTY,
                  ms.EMPTY if row["repo_id"] is None else str(row["repo_id"])]
                 for row in data["rows"]])


@meta.command("assign")
@click.argument("classroom")
@click.argument("table_file", type=click.File("r"))
@dryrun_option
def meta_assign(classroom, table_file, dryrun):
    """Import a NAME + STUDENTS table and create the repos it describes."""
    gh = get_github()
    org, partial = resolve_classroom(classroom)
    _repo, checkout = _open_meta(gh, org)
    classroom_dir = _resolve_classroom_dir(checkout, partial, classroom)
    data = _load_classroom(checkout, classroom_dir)

    incoming = ms.parse_students_tsv(table_file.read())
    merged, changed_names = ms.merge_rows(data["rows"], incoming)
    data["rows"] = merged

    actions = []
    if changed_names:
        _perform(dryrun, f"record rows: {', '.join(changed_names)}",
                 lambda: None, actions)

    resolve = _make_resolver(gh, org, partial or classroom_dir)
    changed, unresolved = _realize_classroom(gh, org, data, resolve, dryrun, actions)

    if not dryrun and (changed or changed_names):
        ms.save_classroom(checkout, classroom_dir, data["prefix"], data["template"],
                          tas=data["tas"], rows=data["rows"], **_ini_settings(data))
        ms.commit_and_push(checkout, f"assign {classroom_dir}", get_token())

    if not actions:
        output("nothing to do")
    if unresolved:
        sys.exit(1)


def _reconcile_tas_team(gh, org, classroom_dir, ta_logins, universe, dryrun, actions):
    """the classroom's team exists, has exactly the tas, and reads exactly
    the classroom's repos. unrelated team-repo grants are left alone only
    for the meta repo itself."""
    name = tas_team_name(classroom_dir)
    team = get_team(gh, org, name)
    made_team = {}
    if team is None:
        def _create_team():
            made_team["team"] = create_team(gh, org, name)
        _perform(dryrun, f'create team "{name}" in {org}', _create_team, actions)
        team = made_team.get("team")

    current_members = {m.login.lower(): m for m in team.get_members()} if team else {}
    desired_members = {login.lower(): login for login in ta_logins}
    for lowered, login in desired_members.items():
        if lowered not in current_members:
            def _add(login=login):
                (team or made_team["team"]).add_membership(gh.get_user(login))
            _perform(dryrun, f'add {login} to team "{name}"', _add, actions)
    for lowered, member in current_members.items():
        if lowered not in desired_members:
            def _remove(member=member):
                team.remove_membership(member)
            _perform(dryrun, f'remove {member.login} from team "{name}"',
                     _remove, actions)

    team_repos = {r.full_name: r for r in team.get_repos()} if team else {}
    for full_name, repo in universe.items():
        if full_name not in team_repos:
            def _grant(repo=repo):
                (team or made_team["team"]).update_team_repository(repo, "pull")
            _perform(dryrun, f'grant team "{name}" pull on {full_name}',
                     _grant, actions)
    for full_name, repo in team_repos.items():
        if full_name not in universe and repo.name != ms.META_REPO_NAME:
            def _revoke(repo=repo):
                team.remove_from_repos(repo)
            _perform(dryrun, f'revoke team "{name}" from {full_name}',
                     _revoke, actions)


@meta.command("apply")
@click.argument("classroom")
@dryrun_option
def meta_apply(classroom, dryrun):
    """Reconcile the org with the meta repo: repos, TA teams, student access.

    Every classroom directory in the meta repo is reconciled, each with its
    own tas-CLASSROOM team.
    """
    gh = get_github()
    org, _partial = resolve_classroom(classroom)
    _repo, checkout = _open_meta(gh, org)
    classroom_dirs = ms.list_classrooms(checkout)
    if not classroom_dirs:
        error("the meta repo has no classrooms. run: meta init")
        sys.exit(2)

    actions = []
    any_unresolved = []
    all_repos = list_org_repos(gh, org)
    by_id = {r.id: r for r in all_repos}

    for classroom_dir in classroom_dirs:
        data = _load_classroom(checkout, classroom_dir)
        resolve = _make_resolver(gh, org, classroom_dir)
        desired = ms.effective_repo_settings(data)

        # 1. realize rows that don't have a repo yet (hand-added ones included)
        changed, unresolved = _realize_classroom(gh, org, data, resolve, dryrun, actions)
        any_unresolved.extend(unresolved)
        if changed:
            ms.save_classroom(checkout, classroom_dir, data["prefix"], data["template"],
                              tas=data["tas"], rows=data["rows"], **_ini_settings(data))

        # the classroom's repos: prefix matches ∪ recorded ids
        universe = {}
        prefix = (data["prefix"] or "").lower()
        for r in all_repos:
            if prefix and r.name.lower().startswith(prefix):
                universe[r.full_name] = r
        for row in data["rows"]:
            if row["repo_id"] is None:
                continue
            repo = by_id.get(row["repo_id"]) or get_repo_by_id(gh, row["repo_id"])
            if repo is None:
                warn(f"recorded repo for {row['name']} (id {row['repo_id']}) is gone")
                continue
            universe[repo.full_name] = repo
            # 2. students on a realized row are exactly its push collaborators
            logins, unresolved = _resolve_row_students(row, resolve)
            any_unresolved.extend(unresolved)
            _reconcile_row_collaborators(gh, repo, logins, dryrun, actions)
            # and its default branch carries the classroom's protection settings
            _reconcile_repo_protection(repo, desired, dryrun, actions)

        # 3. the classroom's TA team reads exactly the classroom's repos
        ta_logins = []
        for entry in data["tas"]:
            login = resolve(entry)
            if login:
                if login not in ta_logins:
                    ta_logins.append(login)
            else:
                error(f'cannot resolve TA "{entry}" to a github id')
                any_unresolved.append(entry)
        _reconcile_tas_team(gh, org, classroom_dir, ta_logins, universe,
                            dryrun, actions)

    if not dryrun:
        ms.commit_and_push(checkout, "apply", get_token())
    if not actions:
        output("nothing to do")
    if any_unresolved:
        sys.exit(1)
