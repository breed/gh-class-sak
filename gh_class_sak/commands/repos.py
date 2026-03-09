import difflib
from concurrent.futures import ThreadPoolExecutor
import os
import re
import sys

import click

from gh_class_sak.core import (
    gh_class_sak, get_session, output, error, resolve_name,
    get_config, get_canvas, resolve_course_mapping, normalize_course_name,
    config_ini,
)
from gh_class_sak.github_api import (
    list_classrooms, list_assignments, list_accepted_assignments,
    list_collaborators, list_commits, get_user,
)
from gh_class_sak.canvas_api import (
    list_courses, list_group_categories, list_groups_in_category,
    list_group_users, graphql_enrollments, get_user_profile,
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
    for score, repo_idx, group_name in pairs:
        if repo_idx in assigned_repos or group_name in assigned_groups:
            continue
        result[repo_idx] = group_name
        assigned_repos.add(repo_idx)
        assigned_groups.add(group_name)

    return result


def resolve_canvas_course(classroom):
    """Resolve a GitHub classroom to a Canvas course, returning shared context."""
    config = get_config()
    canvas = get_canvas()
    canvas_partial = resolve_course_mapping(config, classroom)

    courses = list_courses(canvas)
    for c in courses:
        c.name = normalize_course_name(c.name)
    course = resolve_name(courses, normalize_course_name(canvas_partial), "canvas course")

    return canvas, course


def fetch_canvas_groups(classroom, group_category, canvas_ctx=None):
    """Fetch Canvas groups for a classroom and group category."""
    if canvas_ctx is None:
        canvas_ctx = resolve_canvas_course(classroom)
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


def fetch_enrollment_data(classroom, canvas_ctx=None):
    """Fetch Canvas enrollment data mapping students to instructors by section."""
    if canvas_ctx is None:
        canvas_ctx = resolve_canvas_course(classroom)
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
            if user_id not in instructors:
                instructors[user_id] = {
                    "name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "section_ids": set(),
                }
            instructors[user_id]["section_ids"].add(section_id)
        elif role == "StudentEnrollment":
            if user_id not in students:
                students[user_id] = {
                    "name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "section_ids": set(),
                }
            students[user_id]["section_ids"].add(section_id)

    # fetch GitHub usernames for instructors from Canvas profiles in parallel
    def _fetch_github(uid):
        try:
            profile = get_user_profile(canvas, uid)
            github = extract_github_username(profile)
            if not github:
                from gh_class_sak.core import warn
                warn(f"no github link found in canvas profile for {instructors[uid]['name']}"
                     f" (fields: {', '.join(profile.keys())})")
            return uid, github
        except Exception as exc:
            from gh_class_sak.core import warn
            warn(f"failed to fetch canvas profile for {instructors[uid]['name']}: {exc}")
            return uid, None

    with ThreadPoolExecutor() as pool:
        for uid, github in pool.map(lambda uid: _fetch_github(uid), instructors):
            instructors[uid]["github"] = github

    return {
        "students": list(students.values()),
        "instructors": list(instructors.values()),
    }


def match_canvas_students(member_logins, user_cache, enrollment_data):
    """Match GitHub logins to Canvas students by name. Returns dict of login -> canvas student."""
    result = {}
    if not enrollment_data:
        return result
    for login in member_logins:
        u = user_cache.get(login, {})
        gh_name = u.get("name", "")
        if not gh_name:
            continue
        for s in enrollment_data["students"]:
            if names_match(gh_name, s["name"]):
                result[login] = s
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
    session = get_session()
    user_cache = {}

    # resolve Canvas course once if any Canvas feature is needed
    need_canvas = (group_category or show_instructors or show_email) and os.path.exists(config_ini)
    canvas_ctx = resolve_canvas_course(classroom) if need_canvas else None

    groups_data = None
    if group_category:
        groups_data = fetch_canvas_groups(classroom, group_category, canvas_ctx)

    enrollment_data = None
    if (show_instructors or show_email) and canvas_ctx:
        enrollment_data = fetch_enrollment_data(classroom, canvas_ctx)

    # resolve classroom
    rooms = list_classrooms(session)
    room = resolve_name(rooms, classroom, "classroom")

    # resolve assignment
    assignments = list_assignments(session, room["id"])
    # assignments use "title" not "name" — normalize for resolve_name
    for a in assignments:
        a.setdefault("name", a.get("title", ""))
    asn = resolve_name(assignments, assignment, "assignment")

    slug = asn.get("slug", "")

    # determine if we need GitHub user profiles (for name matching or annotations)
    need_profiles = (groups_data is not None
                     or enrollment_data is not None
                     or (members and (show_name or show_email)))

    # first pass: collect all rows and compute column widths
    rows = []
    accepted = list_accepted_assignments(session, asn["id"])
    for aa in accepted:
        repo_info = aa.get("repository", {})
        full_name = repo_info.get("full_name", "")
        if not full_name:
            continue
        owner, repo_name = full_name.split("/", 1)

        # derive team name by stripping assignment slug prefix
        if slug and repo_name.startswith(slug + "-"):
            team = repo_name[len(slug) + 1:]
        else:
            team = repo_name

        # fetch collaborators
        collabs = list_collaborators(session, owner, repo_name)
        member_logins = []
        for c in collabs:
            role = c.get("role_name", c.get("permissions", {}).get("admin", False))
            if role == "admin" or role is True:
                continue
            member_logins.append(c["login"])

        # fetch GitHub profiles if needed
        if need_profiles:
            for login in member_logins:
                if login not in user_cache:
                    user_cache[login] = get_user(session, login)

        # extract member emails from commit history
        commit_emails = {}
        if show_email:
            member_set = set(member_logins)
            try:
                commits = list_commits(session, owner, repo_name)
            except Exception:
                commits = []
            for commit in commits:
                author = commit.get("author")
                if not author:
                    continue
                login = author.get("login")
                if login not in member_set or login in commit_emails:
                    continue
                email = commit.get("commit", {}).get("author", {}).get("email", "")
                if email and "@users.noreply.github.com" not in email:
                    commit_emails[login] = email

        # match members to Canvas students once per repo
        canvas_matches = match_canvas_students(member_logins, user_cache, enrollment_data)

        # format member labels
        member_labels = []
        if members:
            for login in member_logins:
                u = user_cache.get(login, {})
                gh_name = u.get("name") if need_profiles else None
                cs = canvas_matches.get(login)
                email = None
                if show_email:
                    commit_email = commit_emails.get(login)
                    canvas_email = cs.get("email") if cs else None
                    if commit_email and canvas_email and commit_email != canvas_email:
                        email = f"{commit_email},{canvas_email}"
                    else:
                        email = commit_email or canvas_email or u.get("email")
                member_labels.append(format_label(login, name=gh_name, email=email,
                                                  show_name=show_name, show_email=show_email))

        # find instructors for this group using cached matches
        instructor_labels = []
        if show_instructors and enrollment_data:
            matched_sections = set()
            for cs in canvas_matches.values():
                matched_sections.update(cs["section_ids"])
            for inst in find_instructors_for_sections(matched_sections, enrollment_data):
                gh = inst.get("github") or "?"
                instructor_labels.append(format_label(gh, name=inst.get("name"),
                                                      email=inst.get("email"),
                                                      show_name=show_name,
                                                      show_email=show_email))

        # collect gh profile names for group matching
        gh_names = []
        if groups_data is not None:
            for login in member_logins:
                u = user_cache.get(login, {})
                if u.get("name"):
                    gh_names.append(u["name"])

        row = {
            "team": team,
            "full_name": full_name,
            "members": ",".join(member_labels),
            "instructors": ",".join(instructor_labels),
            "gh_names": gh_names,
        }
        rows.append(row)

    # global group matching
    if groups_data is not None:
        repos_gh_names = [(i, row["gh_names"]) for i, row in enumerate(rows)]
        group_assignments = match_groups(repos_gh_names, groups_data)
        for i, row in enumerate(rows):
            row["group"] = group_assignments.get(i, "?")
    else:
        for row in rows:
            row["group"] = None

    # filter empty teams (only when members column is shown)
    if members and not show_empty:
        rows = [row for row in rows if row["members"]]

    # build header and columns
    headers = ["TEAM"]
    if repo:
        headers.append("REPO")
    if members:
        headers.append("MEMBERS")
    if show_instructors:
        headers.append("INSTRUCTORS")
    if groups_data is not None:
        headers.append("GROUP")

    for row in rows:
        cols = [row["team"]]
        if repo:
            cols.append(row["full_name"])
        if members:
            cols.append(row["members"])
        if show_instructors:
            cols.append(row["instructors"])
        if groups_data is not None:
            cols.append(row["group"])
        row["_cols"] = cols

    if not rows:
        return

    num_cols = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row["_cols"]):
            widths[i] = max(widths[i], len(col))

    # print header
    parts = []
    for i, h in enumerate(headers):
        if i < num_cols - 1:
            parts.append(h.ljust(widths[i]))
        else:
            parts.append(h)
    output("  ".join(parts))

    for row in rows:
        parts = []
        for i, col in enumerate(row["_cols"]):
            if i < num_cols - 1:
                parts.append(col.ljust(widths[i]))
            else:
                parts.append(col)
        output("  ".join(parts))


@repos.command("members")
@click.argument("classroom")
@click.argument("assignment")
def repos_members(classroom, assignment):
    """List members and their emails extracted from commit history."""
    session = get_session()

    # resolve classroom and assignment
    rooms = list_classrooms(session)
    room = resolve_name(rooms, classroom, "classroom")

    assignments = list_assignments(session, room["id"])
    for a in assignments:
        a.setdefault("name", a.get("title", ""))
    asn = resolve_name(assignments, assignment, "assignment")

    slug = asn.get("slug", "")
    accepted = list_accepted_assignments(session, asn["id"])

    rows = []
    for aa in accepted:
        repo_info = aa.get("repository", {})
        full_name = repo_info.get("full_name", "")
        if not full_name:
            continue
        owner, repo_name = full_name.split("/", 1)

        if slug and repo_name.startswith(slug + "-"):
            team = repo_name[len(slug) + 1:]
        else:
            team = repo_name

        # scan commits for (login, name, email) triples
        seen = set()
        try:
            commits = list_commits(session, owner, repo_name)
        except Exception:
            continue
        for commit in commits:
            author = commit.get("author")
            login = author.get("login") if author else None
            commit_author = commit.get("commit", {}).get("author", {})
            name = commit_author.get("name", "")
            email = commit_author.get("email", "")
            if not email or "@users.noreply.github.com" in email:
                continue
            key = (login or "", email)
            if key in seen:
                continue
            seen.add(key)
            rows.append((team, login or "?", name, email))

    if not rows:
        return

    # compute column widths
    headers = ("REPO", "GITHUB_ID", "NAME", "EMAIL")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    fmt = "  ".join(f"{{:{w}}}" for w in widths[:-1]) + "  {}"
    output(fmt.format(*headers))
    for row in rows:
        output(fmt.format(*row))


@repos.command("missing")
@click.argument("classroom")
@click.argument("assignment")
@click.option("--group", "group_category", default=None, type=str,
              help="show Canvas groups with no matching repo")
def repos_missing(classroom, assignment, group_category):
    """List students or Canvas groups without repos."""
    session = get_session()

    # resolve classroom and assignment
    rooms = list_classrooms(session)
    room = resolve_name(rooms, classroom, "classroom")

    assignments = list_assignments(session, room["id"])
    for a in assignments:
        a.setdefault("name", a.get("title", ""))
    asn = resolve_name(assignments, assignment, "assignment")

    slug = asn.get("slug", "")
    accepted = list_accepted_assignments(session, asn["id"])

    if group_category:
        groups_data = fetch_canvas_groups(classroom, group_category)
        user_cache = {}

        # collect github profile names per repo
        repos_gh_names = []
        for idx, aa in enumerate(accepted):
            repo_info = aa.get("repository", {})
            full_name = repo_info.get("full_name", "")
            if not full_name:
                continue
            owner, repo_name = full_name.split("/", 1)

            collabs = list_collaborators(session, owner, repo_name)
            gh_names = []
            for c in collabs:
                role = c.get("role_name", c.get("permissions", {}).get("admin", False))
                if role == "admin" or role is True:
                    continue
                login = c["login"]
                if login not in user_cache:
                    user_cache[login] = get_user(session, login)
                u = user_cache[login]
                if u.get("name"):
                    gh_names.append(u["name"])
            repos_gh_names.append((idx, gh_names))

        group_assignments = match_groups(repos_gh_names, groups_data)
        matched_groups = set(group_assignments.values())

        # output unmatched groups
        rows = []
        for g in groups_data:
            if g["name"] not in matched_groups:
                rows.append((g["name"], ",".join(g["members"])))

        if not rows:
            return

        name_width = max(len(r[0]) for r in rows)
        for name, members in rows:
            output(f"{name.ljust(name_width)}  {members}")
    else:
        # without --group: list accepted assignments with no repo
        missing = []
        for aa in accepted:
            repo_info = aa.get("repository", {})
            full_name = repo_info.get("full_name", "")
            if full_name:
                continue
            students = aa.get("students", [])
            group = aa.get("group", {})
            if group and group.get("name"):
                missing.append(f"{group['name']}: {','.join(s.get('login', '?') for s in students)}")
            elif students:
                for s in students:
                    missing.append(s.get("login", "?"))

        for m in missing:
            output(m)
