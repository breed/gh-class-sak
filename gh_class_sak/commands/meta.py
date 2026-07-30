import os
import re
import sys

import click

from gh_class_sak import meta_store as ms
from gh_class_sak.commands.repos import Classroom, fetch_enrollment_data, print_table
from gh_class_sak.core import (
    add_org_to_config,
    config_ini,
    configured_orgs,
    dryrun_option,
    error,
    get_github,
    get_token,
    gh_class_sak,
    has_canvas_config,
    info,
    match_org,
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
    team_name,
)

REPO_SETTING_KEYS = ("protection", "linear_history", "force_push")


def tas_team_name(classroom_dir):
    """each classroom gets its own COURSENAME-tas team, so TAs of one
    classroom in an org don't gain access to another classroom's repos."""
    return f"{classroom_dir}-tas"


def _check_assignment_name(name):
    """the name becomes both a file name and a repo-name segment."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        error(f'assignment name "{name}" must be letters, digits, ".", "_", or "-"')
        sys.exit(2)


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
            error(f'no {ms.META_REPO_NAME} repo in "{org}". create one with: meta init')
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
            if has_canvas_config() and course_partial:
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

    covers every assignment in the classroom. mutates rows in place under
    --no-dryrun. returns (changed, unresolved).
    """
    template = _template_repo(gh, data)
    desired = ms.effective_repo_settings(data)
    changed = False
    all_unresolved = []
    for assignment, rows in data["assignments"].items():
        for row in rows:
            if row["repo_id"] is not None:
                continue
            logins, unresolved = _resolve_row_students(row, resolve)
            all_unresolved.extend(unresolved)
            repo_name = ms.join_repo_name(data["prefix"], assignment, row["name"])
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
    """Manage the org's classroom-meta repo: one directory per classroom."""
    pass


def _pick_org(org_option, classroom):
    """the org hosting a new classroom: --org, the single configured org, or
    — with no config — the classroom argument itself."""
    orgs = configured_orgs()
    if org_option:
        return match_org(org_option, orgs) or org_option
    if len(orgs) == 1:
        return orgs[0]
    if orgs:
        error("several orgs are configured; pass --org. orgs:")
        for candidate in orgs:
            error(f"    {candidate}")
        sys.exit(2)
    return classroom


@meta.command("init")
@click.argument("classroom")
@click.option("--org", default=None,
              help="the github org hosting the classroom"
                   " (required when several orgs are configured)")
@click.option("--prefix", default=None,
              help="the repo-name prefix for the classroom's repos (optional)")
@click.option("--template", default=None,
              help="OWNER/NAME template repo for created assignment repos")
@dryrun_option
def meta_init(classroom, org, prefix, template, dryrun):
    """Create the classroom-meta repo and record CLASSROOM (a course name) in it."""
    gh = get_github()
    org = _pick_org(org, classroom)
    classroom_dir = normalize_course_name(classroom)

    meta_repo, checkout = _open_meta(gh, org, required=False)
    existing = _load_classroom(checkout, classroom_dir) if checkout else None

    if prefix is None and existing:
        prefix = existing["prefix"]
    if template is None and existing:
        template = existing["template"]

    tas = list(existing["tas"]) if existing else []
    if has_canvas_config():
        data = fetch_enrollment_data(Classroom(org, classroom_dir))
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
        # assignments arrive later, via meta assign or hand-added tsv files
        ms.save_classroom(checkout_now, classroom_dir, prefix, template,
                          tas=tas, **settings)
        ms.commit_and_push(checkout_now, f"init {classroom_dir}", get_token())
    _perform(dryrun,
             f"record {classroom_dir}: prefix={prefix or '-'}"
             + (f" template={template}" if template else "")
             + f" tas={','.join(tas) or '-'}",
             _write, actions)


@meta.command("show")
@click.argument("classroom")
def meta_show(classroom):
    """Show a classroom's recorded state."""
    gh = get_github()
    org, partial = resolve_classroom(gh, classroom)
    _repo, checkout = _open_meta(gh, org)
    classroom_dir = _resolve_classroom_dir(checkout, partial, classroom)
    data = _load_classroom(checkout, classroom_dir)

    protection, linear_history, force_push = ms.effective_repo_settings(data)
    output(f"CLASSROOM {classroom_dir}")
    output(f"PREFIX    {data['prefix'] or '-'}")
    if data["template"]:
        output(f"TEMPLATE  {data['template']}")
    output(f"TAS       {','.join(data['tas']) or '-'}")
    output(f"SETTINGS  protection={protection}"
           f" linear_history={str(linear_history).lower()}"
           f" force_push={str(force_push).lower()}")
    if not data["assignments"]:
        output("")
        output("(no assignments)")
    for name, rows in data["assignments"].items():
        output("")
        output(f"ASSIGNMENT {name}")
        print_table(list(ms.STUDENTS_HEADERS),
                    [[row["name"],
                      ",".join(row["students"]) or ms.EMPTY,
                      row["repo"] or ms.EMPTY,
                      ms.EMPTY if row["repo_id"] is None else str(row["repo_id"])]
                     for row in rows])


@meta.command("assign")
@click.argument("classroom")
@click.argument("table_file", type=click.File("r"))
@click.option("--assignment", default=None,
              help="assignment name (default: the table file's basename)")
@dryrun_option
def meta_assign(classroom, table_file, assignment, dryrun):
    """Import a NAME + STUDENTS table as an assignment and create its repos."""
    gh = get_github()
    org, partial = resolve_classroom(gh, classroom)
    _repo, checkout = _open_meta(gh, org)
    classroom_dir = _resolve_classroom_dir(checkout, partial, classroom)
    data = _load_classroom(checkout, classroom_dir)

    if assignment is None and table_file.name in ("-", "<stdin>"):
        error("--assignment is required when the table comes from stdin")
        sys.exit(2)
    name = assignment or os.path.splitext(os.path.basename(table_file.name))[0]
    _check_assignment_name(name)

    incoming = ms.parse_students_tsv(table_file.read())
    merged, changed_names = ms.merge_rows(data["assignments"].get(name, []), incoming)
    data["assignments"][name] = merged
    data["assignments"] = dict(sorted(data["assignments"].items()))

    actions = []
    if changed_names:
        _perform(dryrun, f"record {name} rows: {', '.join(changed_names)}",
                 lambda: None, actions)

    resolve = _make_resolver(gh, org, partial or classroom_dir)
    changed, unresolved = _realize_classroom(gh, org, data, resolve, dryrun, actions)

    if not dryrun and (changed or changed_names):
        ms.save_classroom(checkout, classroom_dir, data["prefix"], data["template"],
                          tas=data["tas"], assignments=data["assignments"],
                          **_ini_settings(data))
        ms.commit_and_push(checkout, f"assign {classroom_dir}/{name}", get_token())

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
    """Reconcile the org with the classroom-meta repo: repos, TA teams, student access.

    Every classroom directory in the classroom-meta repo is reconciled, each
    with its own tas-CLASSROOM team.
    """
    gh = get_github()
    org, _partial = resolve_classroom(gh, classroom)
    _repo, checkout = _open_meta(gh, org)
    classroom_dirs = ms.list_classrooms(checkout)
    if not classroom_dirs:
        error("the classroom-meta repo has no classrooms. run: meta init")
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
                              tas=data["tas"], assignments=data["assignments"],
                              **_ini_settings(data))

        # the classroom's repos: per-assignment prefix matches ∪ recorded ids
        universe = {}
        for assignment in data["assignments"]:
            joined = ms.join_repo_name(data["prefix"], assignment).lower()
            for r in all_repos:
                if r.name.lower().startswith(joined):
                    universe[r.full_name] = r
        for rows in data["assignments"].values():
            for row in rows:
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


@gh_class_sak.command("migrate-github-classroom")
@click.argument("org")
@dryrun_option
def migrate_github_classroom(org, dryrun):
    """Import ORG's GitHub Classroom leftovers into the classroom-meta repo.

    GitHub Classroom named repos ASSIGNMENT-TEAM but kept no course marker,
    so this scans ORG's repos, infers the assignments from shared name
    prefixes, and asks which course each one belongs to (blank skips it) and
    what to call it. Every imported row records the repo's collaborators as
    the students plus its url and permanent id, so it is tracked from day
    one. ORG is added to the config's [ORGS] when it isn't there yet.
    """
    gh = get_github()
    orgs = configured_orgs()
    org = match_org(org, orgs) or org

    repos = [r for r in list_org_repos(gh, org) if r.name != ms.META_REPO_NAME]
    inferred = [prefix for prefix, _count in
                infer_assignment_prefixes([r.name for r in repos])]
    if not inferred:
        error(f'no assignment-shaped repo names (PREFIX-TEAM) in "{org}"')
        sys.exit(2)

    # each repo belongs to the most specific assignment prefix that fits it
    grouped = {prefix: [] for prefix in inferred}
    unmatched = []
    for repo in repos:
        fits = [p for p in inferred if repo.name.lower().startswith(p.lower() + "-")]
        if fits:
            grouped[max(fits, key=len)].append(repo)
        else:
            unmatched.append(repo.name)
    if unmatched:
        info(f"ignoring {len(unmatched)} repos matching no assignment:"
             f" {', '.join(sorted(unmatched))}")

    # ask where each inferred assignment belongs before previewing anything
    plan = []  # (classroom_dir, assignment_name, repos)
    for prefix in inferred:
        teams = ", ".join(team_name(r.name, prefix) for r in grouped[prefix])
        info(f'{prefix}: {len(grouped[prefix])} repos ({teams})')
        course = click.prompt(f'  course for "{prefix}" (blank to skip)',
                              default="", show_default=False)
        if not course.strip():
            info(f"  skipping {prefix}")
            continue
        name = click.prompt(f'  assignment name for "{prefix}"', default=prefix)
        _check_assignment_name(name)
        plan.append((normalize_course_name(course.strip()), name, grouped[prefix]))
    if not plan:
        output("nothing to do")
        return

    actions = []
    if org not in orgs:
        def _add_org():
            add_org_to_config(org)
        _perform(dryrun, f"add {org} to [ORGS] in {config_ini}", _add_org, actions)

    meta_repo, checkout = _open_meta(gh, org, required=False)
    if meta_repo is None:
        def _create_meta():
            repo = create_org_repo(gh, org, ms.META_REPO_NAME, auto_init=True)
            ms.checkout_meta(repo.clone_url, org, get_token())
        _perform(dryrun, f"create private {org}/{ms.META_REPO_NAME}",
                 _create_meta, actions)

    by_dir = {}
    for classroom_dir, name, assignment_repos in plan:
        by_dir.setdefault(classroom_dir, []).append((name, assignment_repos))

    writes = []  # (classroom_dir, existing, assignments, tas, changed)
    for classroom_dir, entries in by_dir.items():
        existing = _load_classroom(checkout, classroom_dir) if checkout else None
        assignments = dict(existing["assignments"]) if existing else {}

        members_of = {}
        for _name, assignment_repos in entries:
            for repo in assignment_repos:
                if repo.full_name not in members_of:
                    members, _admins = split_collaborators(repo)
                    members_of[repo.full_name] = [m.login for m in members]
        # a login with write on every one of the classroom's repos is staff,
        # not a student: record it in the tas file instead of every row
        tas_detected = []
        if len(members_of) >= 2:
            common = set.intersection(*(set(m) for m in members_of.values()))
            tas_detected = sorted(common)
        tas = list(existing["tas"]) if existing else []
        new_tas = [login for login in tas_detected if login not in tas]
        if new_tas:
            _perform(dryrun, f"record {classroom_dir} tas: {', '.join(new_tas)}",
                     lambda: None, actions)
        tas += new_tas

        changed_any = bool(new_tas)
        for name, assignment_repos in entries:
            incoming = []
            for repo in assignment_repos:
                students = [login for login in members_of[repo.full_name]
                            if login not in tas_detected]
                incoming.append({"name": team_name(repo.name, name),
                                 "students": students,
                                 "repo": None, "repo_id": None})
            merged, changed = ms.merge_rows(assignments.get(name, []), incoming)
            # adopt each scanned repo's url and permanent id, but never
            # clobber a recorded one
            by_name = {team_name(r.name, name): r for r in assignment_repos}
            for row in merged:
                if row["repo_id"] is None and row["name"] in by_name:
                    row["repo"] = by_name[row["name"]].html_url
                    row["repo_id"] = by_name[row["name"]].id
                    if row["name"] not in changed:
                        changed.append(row["name"])
            assignments[name] = merged
            if changed:
                changed_any = True
                _perform(dryrun, f"record {classroom_dir}/{name}:"
                         f" {', '.join(changed)}", lambda: None, actions)
        writes.append((classroom_dir, existing, assignments, tas, changed_any))

    wrote = False
    for classroom_dir, existing, assignments, tas, changed in writes:
        if not changed and existing is not None:
            continue
        wrote = True
        settings = _ini_settings(existing) if existing else {}

        def _write(classroom_dir=classroom_dir, existing=existing,
                   assignments=assignments, tas=tas, settings=settings):
            checkout_now = ms.meta_checkout_dir(org)
            ms.save_classroom(checkout_now, classroom_dir,
                              existing["prefix"] if existing else None,
                              existing["template"] if existing else None,
                              tas=tas, assignments=assignments, **settings)
        _perform(dryrun, f"record {classroom_dir}: {len(assignments)} assignments,"
                 f" {sum(len(rows) for rows in assignments.values())} teams",
                 _write, actions)
    if wrote and not dryrun:
        ms.commit_and_push(ms.meta_checkout_dir(org), f"migrate {org}", get_token())

    if not actions:
        output("nothing to do")
