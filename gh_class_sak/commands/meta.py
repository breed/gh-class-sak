import os
import re
import shutil
import sys

import click

from gh_class_sak import meta_store as ms
from gh_class_sak.commands.repos import (
    Classroom,
    fetch_canvas_groups,
    fetch_enrollment_data,
    normalize_name,
    print_table,
)
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
    progress,
    resolve_classroom,
    warn,
    would,
)
from gh_class_sak.git_ops import push_template, remote_exists
from gh_class_sak.github_api import (
    UNPROTECTED,
    add_collaborator,
    create_org_repo,
    create_team,
    get_org_repo,
    get_repo_by_id,
    get_team,
    github_safe_name,
    infer_assignment_prefixes,
    list_org_repos,
    matches_prefix,
    pending_invitees,
    protect_default_branch,
    read_default_branch_protection,
    remove_collaborator,
    resolve_email_to_username,
    split_collaborators,
    team_name,
    team_pending_invitations,
)

REPO_SETTING_KEYS = ("protection", "linear_history", "force_push")


def tas_team_name(classroom_dir):
    """each classroom gets its own CLASSROOM-TAs team, so TAs of one
    classroom in an org don't gain access to another classroom's repos."""
    return f"{classroom_dir}-TAs"


def tas_team_slug(classroom_dir):
    """github slugifies the display name to lowercase; lookups need this."""
    return f"{classroom_dir}-tas"


def _check_assignment_name(name):
    """the name becomes both a file name and a repo-name segment."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        error(f'assignment name "{name}" must be letters, digits, ".", "_", or "-"')
        sys.exit(2)


def _derived_course_prefix(entries):
    """the course repo prefix implied by the chosen assignment names.

    when every assignment's name is a '-'-suffix of the repo-name prefix it
    was inferred from, the shared leftover head is the course prefix: repos
    cmpe30-hw1-* with the assignment named hw1 leave cmpe30, and then
    prefix + assignment still spells the real repo names. None when the
    entries disagree or carry no signal.
    """
    heads = set()
    for chosen, inferred, _repos in entries:
        if chosen != inferred and inferred.endswith("-" + chosen):
            heads.add(inferred[:-len(chosen) - 1])
        else:
            return None
    return heads.pop() if len(heads) == 1 else None


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
    except (ValueError, ms.ConfigParserError) as exc:
        error(f"{classroom}/classroom.ini: {exc}")
        sys.exit(2)


def _ini_settings(data):
    """a classroom's raw classroom.ini keys, for passing back through
    save_classroom."""
    keys = REPO_SETTING_KEYS + ("canvas_course", "templates", "group_sets")
    return {key: data[key] for key in keys}


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
        email, github = ms.parse_identity(entry)
        if github:
            return github
        if not email:
            return None
        if entry not in cache:
            cache[entry] = _canvas_lookup(email) or resolve_email_to_username(gh, email)
        return cache[entry]

    return resolve


def _classroom_universe(gh, org, data, all_repos, by_id):
    """the classroom's repos: per-assignment prefix matches ∪ recorded ids."""
    universe = {}
    for assignment in data["assignments"]:
        joined = ms.join_repo_name(data["prefix"], assignment)
        for r in all_repos:
            if matches_prefix(r.name, joined):
                universe[r.full_name] = r
    for rows in data["assignments"].values():
        for row in rows:
            if row["repo_id"] is None:
                continue
            repo = by_id.get(row["repo_id"]) or get_repo_by_id(gh, row["repo_id"])
            if repo is not None:
                universe[repo.full_name] = repo
    return universe


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
        content_url = data["templates"].get(assignment)
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
                if content_url:
                    # the assignment's [TEMPLATE] record: its content, as a
                    # single fresh commit, seeds the new repo
                    source = f" from {content_url}"
                    def _create(repo_name=repo_name, made=made,
                                content_url=content_url):
                        made["repo"] = create_org_repo(gh, org, repo_name)
                        push_template(content_url, made["repo"].clone_url,
                                      get_token())
                else:
                    source = f" from {template.full_name}" if template else ""
                    def _create(repo_name=repo_name, made=made):
                        made["repo"] = create_org_repo(gh, org, repo_name,
                                                       template=template)
                _perform(dryrun, f"create private {org}/{repo_name}{source}", _create, actions)
                if desired != UNPROTECTED:
                    if template is not None or content_url:
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
              help="the repo-name prefix for the classroom's repos"
                   ' (default: the classroom argument; --prefix "" for none)')
@click.option("--template", default=None,
              help="OWNER/NAME template repo for created assignment repos")
@click.option("--canvas-course", default=None,
              help="the canvas course name to record in classroom.ini")
@dryrun_option
def meta_init(classroom, org, prefix, template, canvas_course, dryrun):
    """Create the classroom-meta repo and record CLASSROOM (a course name) in it."""
    gh = get_github()
    org = _pick_org(org, classroom)
    classroom_dir = normalize_course_name(classroom)

    meta_repo, checkout = _open_meta(gh, org, required=False)
    existing = _load_classroom(checkout, classroom_dir) if checkout else None

    if prefix is None and existing:
        prefix = existing["prefix"]
    elif prefix is None:
        # a new classroom namespaces its repos by its own name; migrated
        # classrooms keep whatever they recorded (their assignment names may
        # already carry the prefix), so this only fires for new directories
        prefix = github_safe_name(classroom)
    if template is None and existing:
        template = existing["template"]
    if canvas_course is None and existing:
        canvas_course = existing["canvas_course"]

    tas = list(existing["tas"]) if existing else []
    if has_canvas_config():
        known_emails, known_githubs = set(), set()
        for entry in tas:
            known_email, known_github = ms.parse_identity(entry)
            if known_email:
                known_emails.add(known_email.lower())
            if known_github:
                known_githubs.add(known_github.lower())
        data = fetch_enrollment_data(Classroom(org, canvas_course or classroom_dir))
        for inst in data["instructors"]:
            email, github = inst.get("email"), inst.get("github")
            if not email and not github:
                continue
            if (github and github.lower() in known_githubs) or \
                    (email and email.lower() in known_emails):
                continue
            tas.append(ms.format_identity(email, github))
            if email:
                known_emails.add(email.lower())
            if github:
                known_githubs.add(github.lower())
    elif not tas:
        warn("no canvas config; seed the [TAS] section by hand")

    actions = []
    if meta_repo is None:
        def _create_meta():
            repo = create_org_repo(gh, org, ms.META_REPO_NAME, auto_init=True)
            ms.checkout_meta(repo.clone_url, org, get_token())
        _perform(dryrun, f"create private {org}/{ms.META_REPO_NAME}", _create_meta, actions)

    settings = _ini_settings(existing) if existing else {}
    settings["canvas_course"] = canvas_course

    def _write():
        checkout_now = ms.meta_checkout_dir(org)
        # assignments arrive later, via meta assign or hand-added tsv files
        ms.save_classroom(checkout_now, classroom_dir, prefix, template,
                          tas=tas, **settings)
        ms.commit_and_push(checkout_now, f"init {classroom_dir}", get_token())
    _perform(dryrun,
             f"record {classroom_dir}: prefix={prefix or '-'}"
             + (f" template={template}" if template else "")
             + (f" canvas_course={canvas_course}" if canvas_course else "")
             + f" tas={','.join(tas) or '-'}",
             _write, actions)

    # the classroom's TA team exists from day one, with read access to
    # whatever repos the classroom already has (usually none yet)
    resolve = _make_resolver(gh, org, canvas_course or classroom_dir)
    ta_logins = []
    unresolved = []
    for entry in tas:
        login = resolve(entry)
        if login:
            if login not in ta_logins:
                ta_logins.append(login)
        else:
            error(f'cannot resolve TA "{entry}" to a github id')
            unresolved.append(entry)
    universe = {}
    if existing and existing["assignments"]:
        all_repos = list_org_repos(gh, org)
        by_id = {r.id: r for r in all_repos}
        universe = _classroom_universe(gh, org, existing, all_repos, by_id)
    _reconcile_tas_team(gh, org, classroom_dir, ta_logins, universe, dryrun, actions)
    if unresolved:
        sys.exit(1)


def _mark_students(row, repo):
    """the row's students, each marked with its live repo membership:
    ✅ collaborator, 📧 invited but not yet accepted, ❌ neither."""
    if repo is None:
        return ",".join(row["students"]) or ms.EMPTY
    collaborators = {c.login.lower() for c in repo.get_collaborators()}
    invited = {login.lower() for login in pending_invitees(repo)}
    cells = []
    for student in row["students"]:
        _email, github = ms.parse_identity(student)
        lowered = (github or student).lower()
        if lowered in collaborators:
            cells.append(f"\N{WHITE HEAVY CHECK MARK}{student}")
        elif lowered in invited:
            cells.append(f"\N{E-MAIL SYMBOL}{student}")
        else:
            cells.append(f"\N{CROSS MARK}{student}")
    return ",".join(cells) or ms.EMPTY


def _tas_team_line(gh, org, classroom_dir, configured_tas):
    """how the classroom's tas team compares to the configured [TAS] section."""
    name = tas_team_name(classroom_dir)
    team = get_team(gh, org, tas_team_slug(classroom_dir))
    if team is None:
        return f"TAS TEAM  {name} (not created — run: meta apply)"
    members = {m.login.lower() for m in team.get_members()}
    pending = {u.login.lower() for u in team_pending_invitations(team)}
    configured = {}
    for entry in configured_tas:
        _email, github = ms.parse_identity(entry)
        configured[(github or entry).lower()] = entry
    missing = sorted(entry for key, entry in configured.items()
                     if key not in members and key not in pending)
    invited = sorted(entry for key, entry in configured.items()
                     if key in pending)
    extra = sorted((members | pending) - set(configured))
    if not missing and not invited and not extra:
        return f"TAS TEAM  {name} (matches tas)"
    parts = []
    if invited:
        parts.append("invited, not yet accepted: " + ", ".join(invited))
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if extra:
        parts.append("extra: " + ", ".join(extra))
    return f"TAS TEAM  {name} ({'; '.join(parts)})"


@meta.command("show")
@click.argument("classroom")
def meta_show(classroom):
    """Show a classroom's recorded state, checked against the live org."""
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
    output(_tas_team_line(gh, org, classroom_dir, data["tas"]))
    output(f"SETTINGS  protection={protection}"
           f" linear_history={str(linear_history).lower()}"
           f" force_push={str(force_push).lower()}")

    by_id = {r.id: r for r in list_org_repos(gh, org)}
    if not data["assignments"]:
        output("")
        output("(no assignments)")
    marked = False
    for name, rows in data["assignments"].items():
        table = []
        for row in progress(rows, f"checking {name}"):
            repo = None
            if row["repo_id"] is not None:
                repo = by_id.get(row["repo_id"]) or get_repo_by_id(gh, row["repo_id"])
                if repo is None:
                    warn(f"recorded repo for {row['name']}"
                         f" (id {row['repo_id']}) is gone")
            students = _mark_students(row, repo)
            marked = marked or students != (",".join(row["students"]) or ms.EMPTY)
            table.append([row["name"], students,
                          row["repo"] or ms.EMPTY,
                          ms.EMPTY if row["repo_id"] is None else str(row["repo_id"])])
        output("")
        output(f"ASSIGNMENT {name}")
        print_table(list(ms.STUDENTS_HEADERS), table)
    if marked:
        output("")
        output("markers: \N{WHITE HEAVY CHECK MARK} collaborator"
               "   \N{E-MAIL SYMBOL} invited, not yet accepted"
               "   \N{CROSS MARK} not a collaborator")


@meta.command("delete")
@click.argument("classroom")
@click.option("--delete-repo/--no-delete-repo", default=False,
              help="also delete the assignments' github repos (default: keep them)")
@dryrun_option
def meta_delete(classroom, delete_repo, dryrun):
    """Delete a classroom from the classroom-meta repo, after confirmation.

    An empty classroom asks for a simple yes; one with assignments asks you
    to type the full name of one of them. The github repos survive unless
    --delete-repo says otherwise.
    """
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
    if data["canvas_course"]:
        output(f"CANVAS    {data['canvas_course']}")
    output(f"TAS       {','.join(data['tas']) or '-'}")
    output(f"SETTINGS  protection={protection}"
           f" linear_history={str(linear_history).lower()}"
           f" force_push={str(force_push).lower()}")

    if data["assignments"]:
        output("ASSIGNMENTS " + ", ".join(
            f"{name} ({len(rows)} teams)"
            for name, rows in data["assignments"].items()))
        answer = click.prompt(
            "type the full name of one of the assignments to confirm deletion")
        if answer not in data["assignments"]:
            error(f'"{answer}" is not one of the assignments; nothing deleted')
            sys.exit(2)
    elif not click.confirm(f'delete the empty classroom "{classroom_dir}"?',
                           default=False):
        output("nothing to do")
        return

    actions = []
    if delete_repo:
        by_id = {r.id: r for r in list_org_repos(gh, org)}
        for rows in data["assignments"].values():
            for row in rows:
                if row["repo_id"] is None:
                    continue
                repo = by_id.get(row["repo_id"]) or get_repo_by_id(gh, row["repo_id"])
                if repo is None:
                    warn(f"recorded repo for {row['name']}"
                         f" (id {row['repo_id']}) is gone")
                    continue

                def _delete(repo=repo):
                    repo.delete()
                _perform(dryrun, f"delete repo {repo.full_name}", _delete, actions)

    def _remove():
        shutil.rmtree(ms.classroom_dir(checkout, classroom_dir))
        ms.commit_and_push(checkout, f"delete {classroom_dir}", get_token())
    _perform(dryrun, f"delete classroom {classroom_dir}"
             f" from {org}/{ms.META_REPO_NAME}", _remove, actions)


def _rows_from_canvas(room, canvas_group, unresolvable):
    """assignment rows built from the canvas roster.

    without a group set: one row per enrolled person — students, instructors,
    and TAs alike — named by their github-safe name, carrying their github id
    (or email, to be resolved later). with one: one row per group in the set.
    """
    enrollment = fetch_enrollment_data(room, resolve_students=True)
    people = enrollment["students"] + enrollment["instructors"]

    def _entry(person):
        email, github = person.get("email"), person.get("github")
        if not email and not github:
            error(f'no github id or email in canvas for "{person.get("name")}"')
            unresolvable.append(person.get("name"))
            return None
        return ms.format_identity(email, github)

    if canvas_group is None:
        rows = []
        for person in people:
            entry = _entry(person)
            if entry:
                rows.append({"name": github_safe_name(person["name"]),
                             "students": [entry], "repo": None, "repo_id": None})
        return rows

    by_name = {normalize_name(p["name"]): p for p in people if p.get("name")}
    rows = []
    for group in fetch_canvas_groups(room, canvas_group):
        entries = []
        for member in group["members"]:
            person = by_name.get(normalize_name(member))
            if person is None:
                error(f'cannot find an enrollment for group member "{member}"')
                unresolvable.append(member)
                continue
            entry = _entry(person)
            if entry:
                entries.append(entry)
        rows.append({"name": github_safe_name(group["name"]),
                     "students": entries, "repo": None, "repo_id": None})
    return rows


@meta.command("assign")
@click.argument("classroom")
@click.argument("table_file", type=click.File("r"), required=False)
@click.option("--assignment", default=None,
              help="assignment name (default: the table file's basename;"
                   " required with --from-canvas)")
@click.option("--from-canvas", is_flag=True,
              help="build the table from the canvas roster instead of a file")
@click.option("--canvas-group", default=None,
              help="with --from-canvas: one row per group in this canvas group set")
@click.option("--template", "template_url", default=None,
              help="REPO_URL whose content seeds this assignment's new repos;"
                   " recorded in classroom.ini [TEMPLATE]")
@dryrun_option
def meta_assign(classroom, table_file, assignment, from_canvas, canvas_group,
                template_url, dryrun):
    """Import a NAME + STUDENTS table as an assignment and create its repos."""
    if from_canvas and table_file is not None:
        error("--from-canvas replaces the table file; pass one or the other")
        sys.exit(2)
    if not from_canvas and table_file is None:
        error("pass a table file, or --from-canvas to build one from the roster")
        sys.exit(2)
    if canvas_group and not from_canvas:
        error("--canvas-group only makes sense with --from-canvas")
        sys.exit(2)
    if from_canvas and not assignment:
        error("--assignment is required with --from-canvas")
        sys.exit(2)
    if from_canvas and not has_canvas_config():
        error(f"--from-canvas needs a [CANVAS] section in {config_ini}")
        sys.exit(2)

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

    actions = []
    unresolvable = []
    group_set_changed = False
    template_changed = False
    if template_url:
        if not remote_exists(template_url, get_token()):
            error(f'template repo "{template_url}" is not a reachable git repo')
            sys.exit(2)
        if data["templates"].get(name) != template_url:
            template_changed = True
            data["templates"] = {**data["templates"], name: template_url}
            _perform(dryrun, f"record {name} template: {template_url}",
                     lambda: None, actions)
    course = partial or data["canvas_course"] or classroom_dir
    if from_canvas:
        incoming = _rows_from_canvas(Classroom(org, course), canvas_group,
                                     unresolvable)
        if canvas_group and data["group_sets"].get(name) != canvas_group:
            group_set_changed = True
            data["group_sets"] = {**data["group_sets"], name: canvas_group}
            _perform(dryrun, f"record {name} group set: {canvas_group}",
                     lambda: None, actions)
    else:
        incoming = ms.parse_students_tsv(table_file.read())

    merged, changed_names = ms.merge_rows(data["assignments"].get(name, []), incoming)
    data["assignments"][name] = merged
    data["assignments"] = dict(sorted(data["assignments"].items()))

    if changed_names:
        _perform(dryrun, f"record {name} rows: {', '.join(changed_names)}",
                 lambda: None, actions)

    resolve = _make_resolver(gh, org, course)
    changed, unresolved = _realize_classroom(gh, org, data, resolve, dryrun, actions)
    unresolved = unresolvable + unresolved

    if not dryrun and (changed or changed_names or group_set_changed
                       or template_changed):
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
    team = get_team(gh, org, tas_team_slug(classroom_dir))
    made_team = {}
    if team is None:
        def _create_team():
            made_team["team"] = create_team(gh, org, name)
        _perform(dryrun, f'create team "{name}" in {org}', _create_team, actions)
        team = made_team.get("team")

    current_members = {}
    if team is not None:
        current_members = {m.login.lower(): m for m in team.get_members()}
        # invited-but-not-accepted counts as present, or we re-invite forever
        for user in team_pending_invitations(team):
            current_members.setdefault(user.login.lower(), user)
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

    Naming a classroom reconciles just that one; naming the org reconciles
    every classroom directory, each with its own CLASSROOM-TAs team.
    """
    gh = get_github()
    org, partial = resolve_classroom(gh, classroom)
    _repo, checkout = _open_meta(gh, org)
    if partial:
        classroom_dirs = [_resolve_classroom_dir(checkout, partial, classroom)]
    else:
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
        resolve = _make_resolver(gh, org, data["canvas_course"] or classroom_dir)
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
            joined = ms.join_repo_name(data["prefix"], assignment)
            for r in all_repos:
                if matches_prefix(r.name, joined):
                    universe[r.full_name] = r
        recorded = [row for rows in data["assignments"].values()
                    for row in rows if row["repo_id"] is not None]
        for row in progress(recorded, f"checking {classroom_dir}"):
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
    plan = []  # (classroom_dir, chosen_name, inferred_prefix, repos)
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
        plan.append((normalize_course_name(course.strip()), name, prefix,
                     grouped[prefix]))
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
    for classroom_dir, name, inferred_prefix, assignment_repos in plan:
        by_dir.setdefault(classroom_dir, []).append(
            (name, inferred_prefix, assignment_repos))

    writes = []  # (classroom_dir, existing, prefix, assignments, tas, changed)
    for classroom_dir, entries in by_dir.items():
        existing = _load_classroom(checkout, classroom_dir) if checkout else None
        assignments = dict(existing["assignments"]) if existing else {}

        course_prefix = existing["prefix"] if existing \
            else _derived_course_prefix(entries)
        if existing is None and course_prefix:
            _perform(dryrun, f"record {classroom_dir} prefix: {course_prefix}",
                     lambda: None, actions)

        members_of = {}
        scan = [repo for _name, _inferred, repos_ in entries for repo in repos_]
        for repo in progress(scan, f"reading collaborators for {classroom_dir}"):
            if repo.full_name not in members_of:
                members, _admins = split_collaborators(repo)
                members_of[repo.full_name] = [m.login for m in members]
        # a login with write on every one of the classroom's repos is staff,
        # not a student: record it in [TAS] instead of every row
        tas_detected = []
        if len(members_of) >= 2:
            common = set.intersection(*(set(m) for m in members_of.values()))
            tas_detected = sorted(common)
        tas = list(existing["tas"]) if existing else []
        known_githubs = set()
        for entry in tas:
            _email, github = ms.parse_identity(entry)
            if github:
                known_githubs.add(github.lower())
        new_tas = [ms.format_identity(None, login) for login in tas_detected
                   if login.lower() not in known_githubs]
        if new_tas:
            _perform(dryrun, f"record {classroom_dir} tas: {', '.join(new_tas)}",
                     lambda: None, actions)
        tas += new_tas

        changed_any = bool(new_tas)
        for name, inferred_prefix, assignment_repos in entries:
            incoming = []
            for repo in assignment_repos:
                students = [ms.format_identity(None, login)
                            for login in members_of[repo.full_name]
                            if login not in tas_detected]
                # the team is the repo name minus the repo-name prefix the
                # assignment was inferred from, whatever the assignment is
                # called now
                incoming.append({"name": team_name(repo.name, inferred_prefix),
                                 "students": students,
                                 "repo": None, "repo_id": None})
            merged, changed = ms.merge_rows(assignments.get(name, []), incoming)
            # adopt each scanned repo's url and permanent id, but never
            # clobber a recorded one
            by_name = {team_name(r.name, inferred_prefix): r
                       for r in assignment_repos}
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
        writes.append((classroom_dir, existing, course_prefix, assignments, tas,
                       changed_any))

    wrote = False
    for classroom_dir, existing, course_prefix, assignments, tas, changed in writes:
        if not changed and existing is not None:
            continue
        wrote = True
        settings = _ini_settings(existing) if existing else {}

        def _write(classroom_dir=classroom_dir, existing=existing,
                   course_prefix=course_prefix, assignments=assignments,
                   tas=tas, settings=settings):
            checkout_now = ms.meta_checkout_dir(org)
            ms.save_classroom(checkout_now, classroom_dir, course_prefix,
                              existing["template"] if existing else None,
                              tas=tas, assignments=assignments, **settings)
        _perform(dryrun, f"record {classroom_dir}: {len(assignments)} assignments,"
                 f" {sum(len(rows) for rows in assignments.values())} teams",
                 _write, actions)
    if wrote and not dryrun:
        ms.commit_and_push(ms.meta_checkout_dir(org), f"migrate {org}", get_token())

    if not actions:
        output("nothing to do")
