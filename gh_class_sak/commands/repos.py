import difflib
import sys

import click

from gh_class_sak.core import (
    gh_class_sak, get_session, output, error, resolve_name,
    get_config, get_canvas_session, resolve_course_mapping, normalize_course_name,
)
from gh_class_sak.github_api import (
    list_classrooms, list_assignments, list_accepted_assignments,
    list_collaborators, get_user,
)
from gh_class_sak.canvas_api import (
    list_courses, list_group_categories, list_groups_in_category,
    list_group_users,
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


def fetch_canvas_groups(classroom, group_category):
    """Fetch Canvas groups for a classroom and group category."""
    config = get_config()
    canvas_session, canvas_url = get_canvas_session()
    canvas_partial = resolve_course_mapping(config, classroom)

    courses = list_courses(canvas_session, canvas_url)
    for c in courses:
        c["name"] = normalize_course_name(c.get("name", ""))
    course = resolve_name(courses, normalize_course_name(canvas_partial), "canvas course")

    categories = list_group_categories(canvas_session, canvas_url, course["id"])
    category = resolve_name(categories, group_category, "group category")

    groups = list_groups_in_category(canvas_session, canvas_url, category["id"])
    groups_data = []
    for g in groups:
        users = list_group_users(canvas_session, canvas_url, g["id"])
        groups_data.append({
            "name": g["name"],
            "members": [u["name"] for u in users if u.get("name")],
        })
    return groups_data


@gh_class_sak.group()
def repos():
    """Manage classroom assignment repositories."""
    pass


@repos.command("list")
@click.argument("classroom")
@click.argument("assignment")
@click.option("--repo", is_flag=True, default=False, help="show repo full name")
@click.option("--name", "show_name", is_flag=True, default=False, help="show member names")
@click.option("--group", "group_category", default=None, type=str,
              help="match Canvas group category (partial name)")
@click.option("--show-empty", is_flag=True, default=False, help="include teams with no members")
def repos_list(classroom, assignment, repo, show_name, group_category, show_empty):
    """List repos for a classroom assignment."""
    session = get_session()
    user_cache = {}

    # if --group is given, fetch canvas groups data up front
    groups_data = None
    if group_category:
        groups_data = fetch_canvas_groups(classroom, group_category)

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

        # format member labels
        member_labels = []
        for login in member_logins:
            if show_name or groups_data is not None:
                if login not in user_cache:
                    user_cache[login] = get_user(session, login)
                u = user_cache[login]
                if show_name and u.get("name"):
                    member_labels.append(f"{login}({u['name']})")
                else:
                    member_labels.append(login)
            else:
                member_labels.append(login)

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

    # filter empty teams
    if not show_empty:
        rows = [row for row in rows if row["members"]]

    # build columns and compute widths
    for row in rows:
        cols = [row["team"]]
        if repo:
            cols.append(row["full_name"])
        cols.append(row["members"])
        if groups_data is not None:
            cols.append(row["group"])
        row["_cols"] = cols

    if not rows:
        return

    num_cols = len(rows[0]["_cols"])
    widths = [0] * num_cols
    for row in rows:
        for i, col in enumerate(row["_cols"]):
            widths[i] = max(widths[i], len(col))

    for row in rows:
        parts = []
        for i, col in enumerate(row["_cols"]):
            if i < num_cols - 1:
                parts.append(col.ljust(widths[i]))
            else:
                parts.append(col)
        output("  ".join(parts))


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
