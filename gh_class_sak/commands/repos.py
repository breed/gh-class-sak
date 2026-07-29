import difflib
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import click

from gh_class_sak.canvas_api import (
    get_user_profile,
    graphql_enrollments,
    list_courses,
    list_group_categories,
    list_group_users,
    list_groups_in_category,
)
from gh_class_sak.core import (
    dryrun_option,
    error,
    get_canvas,
    get_config,
    get_github,
    get_token,
    gh_class_sak,
    load_config,
    normalize_course_name,
    output,
    resolve_classroom,
    resolve_course_mapping,
    resolve_name,
    warn,
    would,
)
from gh_class_sak.github_api import (
    find_assignment_repos,
    list_commit_authors,
    list_org_repos,
    resolve_email_to_username,
    resolve_name_to_username,
    split_collaborators,
)


def normalize_name(name):
    if ", " in name:
        parts = name.split(", ", 1)
        name = f"{parts[1]} {parts[0]}"
    return name.lower().strip()


def names_match(name1, name2, threshold=0.7):
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if n1 == n2:
        return True
    return difflib.SequenceMatcher(None, n1, n2).ratio() >= threshold


def match_groups(repos_gh_names, groups_data):
    """Match repos to canvas groups globally, each group assigned at most once.

    repos_gh_names: list of (repo_index, [gh_name, ...])
    Returns: dict of repo_index -> group_name
    """
    # compute all (repo_index, group_name, score) triples
    pairs = []
    for repo_idx, gh_names in repos_gh_names:
        for group in groups_data:
            score = sum(1 for cn in group["members"]
                        if any(names_match(cn, gn) for gn in gh_names))
            if score > 0:
                pairs.append((score, repo_idx, group["name"]))

    # greedy assignment: highest score first
    pairs.sort(reverse=True)
    assigned_repos = set()
    assigned_groups = set()
    result = {}
    for _score, repo_idx, group_name in pairs:
        if repo_idx in assigned_repos or group_name in assigned_groups:
            continue
        result[repo_idx] = group_name
        assigned_repos.add(repo_idx)
        assigned_groups.add(group_name)

    return result


class Classroom:
    """A resolved classroom: the GitHub org plus the Canvas course it maps to.

    course_partial is None when the org hosts several Canvas courses and the
    argument didn't say which; Canvas lookups then report the ambiguity.
    """

    def __init__(self, org, course_partial):
        self.org = org
        self.course_partial = course_partial


def resolve_assignment_repos(classroom, assignment):
    """Resolve a classroom/assignment pair to the repos backing it.

    Returns (Classroom, [(team, repo)]). The classroom argument is a GitHub org
    (or a partial matching one configured in [COURSES]); the assignment is the
    repo name prefix those repos share.
    """
    gh = get_github()
    org, course_partial = resolve_classroom(classroom)
    repos = list_org_repos(gh, org)
    found = find_assignment_repos(repos, assignment)
    if not found:
        error(f'no repos in "{org}" matching assignment "{assignment}". repos are:')
        for r in repos:
            error(f"    {r.name}")
        sys.exit(2)
    return Classroom(org, course_partial), found


def resolve_canvas_course(room):
    """Resolve a classroom to a Canvas course, returning shared context."""
    config = get_config()
    canvas = get_canvas()
    course_partial = room.course_partial or resolve_course_mapping(config, room.org)

    courses = list_courses(canvas)
    for c in courses:
        c.name = normalize_course_name(c.name)
    course = resolve_name(courses, normalize_course_name(course_partial), "canvas course")

    return canvas, course


def fetch_canvas_groups(room, group_category, canvas_ctx=None):
    """Fetch Canvas groups for a classroom's course and a group category."""
    if canvas_ctx is None:
        canvas_ctx = resolve_canvas_course(room)
    canvas, course = canvas_ctx

    categories = list_group_categories(course)
    category = resolve_name(categories, group_category, "group category")

    groups = list_groups_in_category(category)
    groups_data = []
    for g in groups:
        users = list_group_users(g)
        groups_data.append({
            "name": g.name,
            "members": [u.name for u in users if u.name],
        })
    return groups_data


_github_re = re.compile(r'github\.com/([a-zA-Z0-9_-]+)')


def extract_github_username(profile):
    """Extract GitHub username from a Canvas user profile."""
    for link in profile.get("links", []):
        url = link.get("url", "") if isinstance(link, dict) else str(link)
        m = _github_re.search(url)
        if m:
            return m.group(1)
    bio = profile.get("bio", "")
    if bio:
        m = _github_re.search(bio)
        if m:
            return m.group(1)
    return None


def _github_from_canvas_profiles(canvas, people):
    """Fill in each person's "github" from their Canvas profile, in parallel.

    Only Canvas is hit concurrently; the GitHub fallbacks below run serially
    because a PyGithub client shares one connection.
    """
    def _fetch(uid):
        try:
            return uid, extract_github_username(get_user_profile(canvas, uid))
        except Exception as exc:
            warn(f"failed to fetch canvas profile for {people[uid]['name']}: {exc}")
            return uid, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        for uid, github in pool.map(_fetch, list(people)):
            people[uid]["github"] = github


def _github_from_search(gh, people):
    """For anyone still unresolved, search GitHub by email then by name."""
    for person in people.values():
        if person.get("github"):
            continue
        github = None
        if person.get("email"):
            github = resolve_email_to_username(gh, person["email"])
        if not github and person.get("name"):
            github = resolve_name_to_username(gh, person["name"])
        person["github"] = github
        if not github:
            warn(f"could not resolve github id for {person['name']}")


def fetch_enrollment_data(room, canvas_ctx=None, gh=None, resolve_students=False):
    """Fetch Canvas enrollment data mapping students to instructors by section."""
    if canvas_ctx is None:
        canvas_ctx = resolve_canvas_course(room)
    canvas, course = canvas_ctx

    # single GraphQL call gets all roles, names, emails, and sections
    nodes = graphql_enrollments(canvas, course.id)

    students = {}
    instructors = {}
    for node in nodes:
        role = node.get("role", {}).get("name", "")
        user = node.get("user", {})
        user_id = user.get("_id")
        if not user_id:
            continue
        section_id = node.get("courseSectionId")

        if role in ("TeacherEnrollment", "TaEnrollment"):
            bucket = instructors
        elif role == "StudentEnrollment":
            bucket = students
        else:
            continue

        if user_id not in bucket:
            bucket[user_id] = {
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "section_ids": set(),
            }
        bucket[user_id]["section_ids"].add(section_id)

    _github_from_canvas_profiles(canvas, instructors)
    if gh:
        _github_from_search(gh, instructors)

    if resolve_students:
        _github_from_canvas_profiles(canvas, students)

    return {
        "students": list(students.values()),
        "instructors": list(instructors.values()),
    }


def match_canvas_students(members, enrollment_data):
    """Match GitHub users to Canvas students by name. Returns dict of login -> student."""
    result = {}
    if not enrollment_data:
        return result
    for m in members:
        gh_name = m.name
        if not gh_name:
            continue
        for s in enrollment_data["students"]:
            if names_match(gh_name, s["name"]):
                result[m.login] = s
                break
    return result


def find_instructors_for_sections(matched_sections, enrollment_data):
    """Find Canvas instructors that share any of the given section IDs."""
    result = []
    seen = set()
    for inst in enrollment_data["instructors"]:
        if inst["section_ids"] & matched_sections:
            key = inst.get("github") or inst["name"]
            if key not in seen:
                seen.add(key)
                result.append(inst)
    return result


def format_label(login, name=None, email=None, show_name=False, show_email=False):
    """Format a user label with optional name/email annotations."""
    annotations = []
    if show_name and name:
        annotations.append(name)
    if show_email and email:
        annotations.append(email)
    if annotations:
        return f"{login}({','.join(annotations)})"
    return login


def print_table(headers, rows):
    """Print space-padded columns; the last column is never padded."""
    if not rows:
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    last = len(headers) - 1
    for row in [headers] + list(rows):
        parts = [col if i == last else col.ljust(widths[i]) for i, col in enumerate(row)]
        output("  ".join(parts))


@gh_class_sak.group()
def repos():
    """Manage classroom assignment repositories."""
    pass


@repos.command("list")
@click.argument("classroom")
@click.argument("assignment")
@click.option("--repo", is_flag=True, default=False, help="show repo full name")
@click.option("--members", is_flag=True, default=False, help="show members column")
@click.option("--instructors", "show_instructors", is_flag=True, default=False,
              help="show instructors column")
@click.option("--name", "show_name", is_flag=True, default=False, help="annotate with names")
@click.option("--email", "show_email", is_flag=True, default=False, help="annotate with emails")
@click.option("--group", "group_category", default=None, type=str,
              help="match Canvas group category (partial name)")
@click.option("--show-empty", is_flag=True, default=False, help="include teams with no members")
def repos_list(classroom, assignment, repo, members, show_instructors, show_name, show_email,
               group_category, show_empty):
    """List repos for a classroom assignment."""
    gh = get_github()
    room, found = resolve_assignment_repos(classroom, assignment)

    # resolve the Canvas course once if any Canvas feature is needed
    need_canvas = (group_category or show_instructors or show_email) and load_config(False)
    canvas_ctx = resolve_canvas_course(room) if need_canvas else None

    groups_data = None
    if group_category:
        groups_data = fetch_canvas_groups(room, group_category, canvas_ctx)

    enrollment_data = None
    if (show_instructors or show_email) and canvas_ctx:
        enrollment_data = fetch_enrollment_data(room, canvas_ctx, gh=gh)

    # a profile name is needed for group matching, canvas matching, or --name
    need_names = (groups_data is not None
                  or enrollment_data is not None
                  or (members and show_name))

    rows = []
    for team, gh_repo in found:
        member_users, _admins = split_collaborators(gh_repo)

        # extract member emails from commit history
        commit_emails = {}
        if show_email:
            member_set = {m.login for m in member_users}
            for login, _name, email in list_commit_authors(gh_repo):
                if login not in member_set or login in commit_emails:
                    continue
                if email and "@users.noreply.github.com" not in email:
                    commit_emails[login] = email

        # match members to Canvas students once per repo
        canvas_matches = match_canvas_students(member_users, enrollment_data) \
            if enrollment_data else {}

        member_labels = []
        if members:
            for m in member_users:
                gh_name = m.name if need_names else None
                cs = canvas_matches.get(m.login)
                email = None
                if show_email:
                    commit_email = commit_emails.get(m.login)
                    canvas_email = cs.get("email") if cs else None
                    if commit_email and canvas_email and commit_email != canvas_email:
                        email = f"{commit_email},{canvas_email}"
                    else:
                        email = commit_email or canvas_email or m.email
                member_labels.append(format_label(m.login, name=gh_name, email=email,
                                                  show_name=show_name, show_email=show_email))

        instructor_labels = []
        if show_instructors and enrollment_data:
            matched_sections = set()
            for cs in canvas_matches.values():
                matched_sections.update(cs["section_ids"])
            for inst in find_instructors_for_sections(matched_sections, enrollment_data):
                instructor_labels.append(format_label(inst.get("github") or "?",
                                                      name=inst.get("name"),
                                                      email=inst.get("email"),
                                                      show_name=show_name,
                                                      show_email=show_email))

        gh_names = []
        if groups_data is not None:
            gh_names = [m.name for m in member_users if m.name]

        rows.append({
            "team": team,
            "full_name": gh_repo.full_name,
            "members": ",".join(member_labels),
            "instructors": ",".join(instructor_labels),
            "gh_names": gh_names,
        })

    # global group matching
    if groups_data is not None:
        assignments = match_groups([(i, r["gh_names"]) for i, r in enumerate(rows)], groups_data)
        for i, row in enumerate(rows):
            row["group"] = assignments.get(i, "?")

    # filter empty teams (only when the members column is shown)
    if members and not show_empty:
        rows = [row for row in rows if row["members"]]

    headers = ["TEAM"]
    keys = ["team"]
    if repo:
        headers.append("REPO")
        keys.append("full_name")
    if members:
        headers.append("MEMBERS")
        keys.append("members")
    if show_instructors:
        headers.append("INSTRUCTORS")
        keys.append("instructors")
    if groups_data is not None:
        headers.append("GROUP")
        keys.append("group")

    print_table(headers, [[row[k] for k in keys] for row in rows])


@repos.command("members")
@click.argument("classroom")
@click.argument("assignment")
def repos_members(classroom, assignment):
    """List members and their emails extracted from commit history."""
    _room, found = resolve_assignment_repos(classroom, assignment)

    rows = []
    for team, gh_repo in found:
        seen = set()
        for login, name, email in list_commit_authors(gh_repo):
            if not email or "@users.noreply.github.com" in email:
                continue
            key = (login or "", email)
            if key in seen:
                continue
            seen.add(key)
            rows.append([team, login or "?", name, email])

    print_table(["REPO", "GITHUB_ID", "NAME", "EMAIL"], rows)


@repos.command("missing")
@click.argument("classroom")
@click.argument("assignment")
@click.option("--group", "group_category", default=None, type=str,
              help="show Canvas groups with no matching repo")
def repos_missing(classroom, assignment, group_category):
    """List Canvas students or groups without repos."""
    gh = get_github()
    room, found = resolve_assignment_repos(classroom, assignment)

    if group_category:
        groups_data = fetch_canvas_groups(room, group_category)

        repos_gh_names = []
        for idx, (_team, gh_repo) in enumerate(found):
            member_users, _admins = split_collaborators(gh_repo)
            repos_gh_names.append((idx, [m.name for m in member_users if m.name]))

        matched_groups = set(match_groups(repos_gh_names, groups_data).values())

        rows = [[g["name"], ",".join(g["members"])]
                for g in groups_data if g["name"] not in matched_groups]
        if not rows:
            return
        name_width = max(len(r[0]) for r in rows)
        for name, group_members in rows:
            output(f"{name.ljust(name_width)}  {group_members}")
        return

    # without --group: Canvas students who are not a collaborator on any repo
    enrollment_data = fetch_enrollment_data(room, gh=gh, resolve_students=True)

    logins = set()
    gh_names = []
    for _team, gh_repo in found:
        member_users, _admins = split_collaborators(gh_repo)
        for m in member_users:
            logins.add(m.login.lower())
            if m.name:
                gh_names.append(m.name)

    rows = []
    for s in enrollment_data["students"]:
        github = s.get("github")
        if github and github.lower() in logins:
            continue
        if any(names_match(s["name"], gn) for gn in gh_names):
            continue
        rows.append([s["name"], s.get("email") or "", github or "?"])

    print_table(["NAME", "EMAIL", "GITHUB_ID"], rows)


@repos.command("clone")
@click.argument("classroom")
@click.argument("assignment")
@click.option("--dest", default=".", type=click.Path(file_okay=False),
              help="directory to clone into (default: current directory)")
@dryrun_option
def repos_clone(classroom, assignment, dest, dryrun):
    """Clone or fast-forward every repo for a classroom assignment."""
    from gh_class_sak.git_ops import clone_or_update

    _room, found = resolve_assignment_repos(classroom, assignment)

    if dryrun:
        for team, gh_repo in found:
            would(f"would clone {gh_repo.full_name} -> {os.path.join(dest, team)}")
        return

    token = get_token()
    os.makedirs(dest, exist_ok=True)
    rows = []
    for team, gh_repo in found:
        target = os.path.join(dest, team)
        status = clone_or_update(gh_repo.clone_url, target, token)
        rows.append([gh_repo.full_name, target, status])

    print_table(["REPO", "PATH", "STATUS"], rows)
