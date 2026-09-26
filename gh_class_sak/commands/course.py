"""The course-centered commands: course, assignment create, and sync.

A COURSE argument is always a course, never an org; --org names the org
when it can't be inferred. The work itself is shared with the meta
commands these replace.
"""
import sys

import click

from gh_class_sak import meta_store as ms
from gh_class_sak.commands import meta as m
from gh_class_sak.core import (
    DRYRUN_FLAGS,
    DRYRUN_HELP,
    UsageOrderGroup,
    announce_dryrun,
    config_ini,
    configured_orgs,
    dryrun_option,
    error,
    get_github,
    get_token,
    gh_class_sak,
    has_canvas_config,
    match_org,
    output,
    progress,
    resolve_course,
    warn,
)
from gh_class_sak.commands.repos import print_table
from gh_class_sak.github_api import get_repo_by_id, list_org_repos, pending_invitees

org_option = click.option(
    "--org", default=None,
    help="the github org hosting the course"
         " (default: search the orgs in the config's [ORGS])")

remove_unlisted_option = click.option(
    "--remove-unlisted-contributors", "remove_unlisted", is_flag=True,
    default=False,
    help="revoke collaborators (and cancel invitations) the assignment rows"
         " don't list; the default only warns about them")


def _org_or_configured(org):
    """[--org], or every configured org when it's not given."""
    if org:
        return [match_org(org, configured_orgs()) or org]
    orgs = configured_orgs()
    if not orgs:
        error(f"pass --org ORG, or list orgs in the [ORGS] section of {config_ini}")
        sys.exit(2)
    return orgs


@gh_class_sak.group("course", cls=UsageOrderGroup, order=(
    "init", "list", "status", "show", "ta", "settings", "delete"))
def course_group():
    """Set up and inspect courses, each hosted in a github org."""
    pass


@course_group.command("init")
@click.argument("course")
@click.option("--org", default=None,
              help="the github org hosting the course"
                   " (required when several orgs are configured)")
@click.option("--prefix", default=None,
              help="the repo-name prefix for the course's repos"
                   ' (default: the course argument; --prefix "" for none)')
@click.option("--template", default=None,
              help="OWNER/NAME template repo for created assignment repos")
@click.option("--canvas-course", default=None,
              help="the canvas course name to record in classroom.ini")
@click.option("--like", "like_course", default=None,
              help="an existing course (last term's) whose TAs, templates, and"
                   " repo settings this new one starts with")
@dryrun_option
def course_init(course, org, prefix, template, canvas_course, like_course, dryrun):
    """Record a new COURSE, creating the org's classroom-meta repo if needed.

    The org is added to the config's [ORGS] when it isn't there yet, so later
    commands find the course without --org.

    \b
    Examples:
      gh-class-sak course init CS-101
      gh-class-sak course init CS-101 --org cs101-fall --apply
      gh-class-sak course init CS-101 --canvas-course "FA26: CS-101" --apply
      gh-class-sak course init CS-101-spring --like CS-101 --apply
    """
    like = None
    if like_course:
        gh = get_github()
        _like_org, like_dir, _checkout, like_data = _open_course(
            gh, like_course, None if configured_orgs() else org)
        like = (like_dir, like_data)
    m._init(course, org, prefix, template, canvas_course, dryrun,
            remember_org=True, like=like)


@course_group.command("list")
@click.argument("course", required=False)
@org_option
def course_list(course, org):
    """List the recorded courses: prefix, TA count, and assignments.

    Without COURSE, every course in --org (or every configured org) is listed.

    \b
    Examples:
      gh-class-sak course list
      gh-class-sak course list --org cs101-fall
    """
    gh = get_github()
    if course:
        org, classroom_dir = resolve_course(gh, course, org)
        m._list(gh, [org], classroom_dir, "COURSE")
    else:
        m._list(gh, _org_or_configured(org), None, "COURSE")


@course_group.command("show")
@click.argument("course")
@org_option
def course_show(course, org):
    """Show a course's recorded state, checked against the live org.

    \b
    Examples:
      gh-class-sak course show CS-101
    """
    gh = get_github()
    m._show(gh, *resolve_course(gh, course, org), course)


@course_group.command("delete")
@click.argument("course")
@org_option
@click.option("--delete-repo/--no-delete-repo", default=False,
              help="also delete the assignments' github repos (default: keep them)")
@dryrun_option
def course_delete(course, org, delete_repo, dryrun):
    """Delete a course from the classroom-meta repo, after confirmation.

    An empty course asks for a simple yes; one with assignments asks you to
    type the full name of one of them. The github repos survive unless
    --delete-repo says otherwise.

    \b
    Examples:
      gh-class-sak course delete CS-101 --apply
    """
    gh = get_github()
    m._delete(gh, *resolve_course(gh, course, org), course, delete_repo, dryrun)


def _open_course(gh, course, org):
    """(org, classroom dir, meta checkout, recorded data) for COURSE."""
    org, classroom_dir = resolve_course(gh, course, org)
    _repo, checkout = m._open_meta(gh, org)
    return org, classroom_dir, checkout, m._load_classroom(checkout, classroom_dir)


def _save_ini(checkout, classroom_dir, data, message):
    """write classroom.ini (no tsvs) and push it."""
    ms.save_classroom(checkout, classroom_dir, data["prefix"], data["template"],
                      tas=data["tas"], **m._ini_settings(data))
    ms.commit_and_push(checkout, message, get_token())


def _identity(entry):
    """the entry in EMAIL/GITHUBID syntax; bare entries parse the legacy way."""
    email, github = ms.parse_identity(entry)
    if not email and not github:
        error(f'"{entry}" is not an identity: use EMAIL/GITHUBID, EMAIL/,'
              " or /GITHUBID")
        sys.exit(2)
    return ms.format_identity(email, github)


def _same_person(a, b):
    """identities sharing a half (case-insensitive) name the same person."""
    email_a, github_a = ms.parse_identity(a)
    email_b, github_b = ms.parse_identity(b)
    return bool((github_a and github_b and github_a.lower() == github_b.lower())
                or (email_a and email_b and email_a.lower() == email_b.lower()))


@course_group.group("ta", cls=UsageOrderGroup, order=("add", "remove"))
def ta_group():
    """Add or remove a course's TAs: the record and the TAs team together.

    An IDENTITY is EMAIL/GITHUBID, EMAIL/ (resolved via the canvas profile's
    github link), or /GITHUBID.
    """
    pass


def _change_tas(gh, org, classroom_dir, checkout, data, tas, dryrun):
    """record the new [TAS] list, then bring the TAs team in line with it."""
    actions = []
    if tas != data["tas"]:
        data = {**data, "tas": tas}
        m._perform(dryrun, f"record {classroom_dir} tas: {', '.join(tas) or '-'}",
                   lambda: _save_ini(checkout, classroom_dir, data,
                                     f"tas {classroom_dir}"),
                   actions)
    resolve = m._make_resolver(org, data["canvas_course"] or classroom_dir)
    failures = []
    logins = m._resolve_tas(data["tas"], resolve, failures)
    all_repos = list_org_repos(gh, org)
    by_id = {r.id: r for r in all_repos}
    universe = m._classroom_universe(gh, org, data, all_repos, by_id)
    m._reconcile_tas_team(gh, org, classroom_dir, logins, universe, dryrun,
                          actions, failures)
    if not actions:
        output("nothing to do")
    m._summarize(actions, dryrun)
    if failures:
        sys.exit(1)


@ta_group.command("add")
@click.argument("course")
@click.argument("identities", metavar="IDENTITY...", nargs=-1, required=True)
@org_option
@dryrun_option
def ta_add(course, identities, org, dryrun):
    """Add TAs to COURSE: record them and invite them to its TAs team.

    \b
    Examples:
      gh-class-sak course ta add CS-101 jane@school.edu/ /msmith --apply
    """
    wanted = [_identity(entry) for entry in identities]
    gh = get_github()
    org, classroom_dir, checkout, data = _open_course(gh, course, org)
    tas = list(data["tas"])
    for entry in wanted:
        if any(_same_person(entry, ta) for ta in tas):
            warn(f"{entry} is already a TA of {classroom_dir}")
        else:
            tas.append(entry)
    _change_tas(gh, org, classroom_dir, checkout, data, tas, dryrun)


@ta_group.command("remove")
@click.argument("course")
@click.argument("identities", metavar="IDENTITY...", nargs=-1, required=True)
@org_option
@dryrun_option
def ta_remove(course, identities, org, dryrun):
    """Remove TAs from COURSE: from the record and from its TAs team.

    Either half of an identity is enough to name the TA.

    \b
    Examples:
      gh-class-sak course ta remove CS-101 msmith --apply
    """
    unwanted = [_identity(entry) for entry in identities]
    gh = get_github()
    org, classroom_dir, checkout, data = _open_course(gh, course, org)
    tas = list(data["tas"])
    for entry, typed in zip(unwanted, identities):
        if not any(_same_person(entry, ta) for ta in tas):
            error(f'"{typed}" is not a TA of {classroom_dir}.'
                  f" its TAs: {', '.join(data['tas']) or 'none'}")
            sys.exit(2)
        tas = [ta for ta in tas if not _same_person(entry, ta)]
    _change_tas(gh, org, classroom_dir, checkout, data, tas, dryrun)


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


@course_group.command("status")
@click.argument("course")
@org_option
def course_status(course, org):
    """What's done and what's left in COURSE, and the command for each step.

    Per assignment: how many rows have a repo, and how many students have
    accepted their invitation, are still invited, or aren't invited yet.
    Then the TAs team, and a to-do list naming the command that fixes
    each gap. Read-only.

    \b
    Examples:
      gh-class-sak course status CS-101
    """
    gh = get_github()
    org, classroom_dir, _checkout, data = _open_course(gh, course, org)
    resolve = m._make_resolver(org, data["canvas_course"] or classroom_dir)
    by_id = {r.id: r for r in list_org_repos(gh, org)}
    canvas = has_canvas_config()
    table, todo = [], []
    for assignment, rows in data["assignments"].items():
        no_repo = gone = accepted = invited = missing = unresolved = 0
        for row in progress(rows, f"checking {assignment}"):
            if row["repo_id"] is None:
                no_repo += 1
                continue
            repo = by_id.get(row["repo_id"]) or get_repo_by_id(gh, row["repo_id"])
            if repo is None:
                gone += 1
                continue
            logins, bad = m._resolve_row_students(row, resolve)
            unresolved += len(bad)
            collaborators = {c.login.lower() for c in repo.get_collaborators()}
            pending = {login.lower() for login in pending_invitees(repo)}
            for login in logins:
                if login.lower() in collaborators:
                    accepted += 1
                elif login.lower() in pending:
                    invited += 1
                else:
                    missing += 1
        have = len(rows) - no_repo - gone
        table.append([assignment, f"{have}/{len(rows)}", str(accepted),
                      str(invited), str(missing + unresolved)])
        sync = f"gh-class-sak sync {classroom_dir} --apply"
        if no_repo:
            todo.append(f"{assignment}: {_plural(no_repo, 'row', 'rows')}"
                        f" without a recorded repo → {sync}")
        if missing:
            todo.append(f"{assignment}: {_plural(missing, 'student', 'students')}"
                        f" not invited yet → {sync}")
        if gone:
            todo.append(f"{assignment}: {_plural(gone, 'recorded repo', 'recorded repos')}"
                        f" gone from github → gh-class-sak course show {classroom_dir}")
        if invited:
            chase = (f"gh-class-sak canvas message-missing {classroom_dir} {assignment}"
                     if canvas else f"gh-class-sak course show {classroom_dir} lists who")
            todo.append(f"{assignment}:"
                        f" {_plural(invited, 'invitation', 'invitations')}"
                        f" not accepted yet → {chase}")
        if unresolved:
            fix = (f"gh-class-sak canvas message-missing {classroom_dir} {assignment}"
                   " asks them to link github" if canvas
                   else f"add their /GITHUBID in {assignment}.tsv")
            todo.append(f"{assignment}:"
                        f" {_plural(unresolved, 'student', 'students')} without a"
                        f" github id → {fix}")

    output(f"COURSE    {classroom_dir}  (org {org})")
    if table:
        print_table(["ASSIGNMENT", "REPOS", "ACCEPTED", "INVITED", "NOT INVITED"],
                    table)
    else:
        todo.append(f"no assignments yet → gh-class-sak assignment create"
                    f" {classroom_dir} NAME --from-canvas")
    tas_line = m._tas_team_line(gh, org, classroom_dir, data["tas"], resolve)
    output(tas_line)
    if not tas_line.endswith("(matches tas)"):
        todo.append(f"TAs team → gh-class-sak sync {classroom_dir} --apply")

    output("")
    if todo:
        output("to do:")
        for line in todo:
            output(f"  {line}")
    else:
        output("all set: every repo exists and every student has accepted")


def _setting_text(value):
    if value is None:
        return "-"
    return str(value).lower() if isinstance(value, bool) else value


@course_group.command("settings")
@click.argument("course")
@org_option
@click.option("--protection", type=click.Choice(ms.PROTECTION_VALUES), default=None,
              help="none, or pr-review: merging needs one approving review")
@click.option("--linear-history/--no-linear-history", default=None,
              help="require a linear history on the default branch")
@click.option("--force-push/--no-force-push", default=None,
              help="allow force pushes to the default branch")
@click.option("--template", default=None,
              help='OWNER/NAME template repo for the course\'s new repos ("" for none)')
@click.option(*DRYRUN_FLAGS, default=True, help=DRYRUN_HELP)
def course_settings(course, org, protection, linear_history, force_push,
                    template, dryrun):
    """Show COURSE's repo settings, or change them.

    A change is recorded and the branch protection is put on every recorded
    repo right away; a template only affects repos created from now on.
    Existing protection is never removed.

    \b
    Examples:
      gh-class-sak course settings CS-101
      gh-class-sak course settings CS-101 --protection pr-review --apply
      gh-class-sak course settings CS-101 --template cs101-fall/starter --apply
    """
    requested = {key: value for key, value in (
        ("protection", protection), ("linear_history", linear_history),
        ("force_push", force_push), ("template", template)) if value is not None}
    gh = get_github()
    org, classroom_dir, checkout, data = _open_course(gh, course, org)
    current = dict(zip(m.REPO_SETTING_KEYS, ms.effective_repo_settings(data)),
                   template=data["template"])
    if not requested:
        output(f"{classroom_dir}: " + " ".join(
            f"{key}={_setting_text(value)}" for key, value in current.items()))
        return

    if dryrun:
        announce_dryrun()
    if "template" in requested:
        requested["template"] = requested["template"] or None
    changed = {key: value for key, value in requested.items()
               if current[key] != value}
    actions = []
    if changed:
        data = {**data, **changed}
        m._perform(dryrun, f"record {classroom_dir} settings: " + " ".join(
                       f"{key}={_setting_text(value)}"
                       for key, value in changed.items()),
                   lambda: _save_ini(checkout, classroom_dir, data,
                                     f"settings {classroom_dir}"),
                   actions)
    if any(key in changed for key in m.REPO_SETTING_KEYS):
        desired = ms.effective_repo_settings(data)
        recorded = [row for rows in data["assignments"].values()
                    for row in rows if row["repo_id"] is not None]
        by_id = {r.id: r for r in list_org_repos(gh, org)}
        for row in progress(recorded, f"protecting {classroom_dir}"):
            repo = by_id.get(row["repo_id"]) or get_repo_by_id(gh, row["repo_id"])
            if repo is None:
                warn(f"recorded repo for {row['name']} (id {row['repo_id']}) is gone")
                continue
            if not m._seed_empty_repo(repo, classroom_dir, desired, dryrun, actions):
                m._reconcile_repo_protection(repo, desired, dryrun, actions)
    if not actions:
        output("nothing to do")
    m._summarize(actions, dryrun)


ROSTER_FORMATS = """\
a roster is one person per line — one repo each:
    jane@school.edu
    /msmith
    rp@school.edu/rpatel
or a table, one repo per row, with comma-joined EMAIL/GITHUBID identities:
    NAME       STUDENTS
    team-1     jane@school.edu/,/msmith
    nightowls  /rpatel,/tk-codes"""


def _parse_roster(text):
    """parse_roster, exiting with both formats shown when the file is bad."""
    try:
        return ms.parse_roster(text)
    except ValueError as exc:
        error(f"cannot read the roster: {exc}")
        for line in ROSTER_FORMATS.splitlines():
            error(line)
        sys.exit(2)


@gh_class_sak.group("assignment")
def assignment_group():
    """Create assignments: one repo per student or group.

    Assignment hw1 of a course with prefix cs101 gets repos like
    cs101-hw1-alice, cs101-hw1-bob.
    """
    pass


@assignment_group.command("create")
@click.argument("course")
@click.argument("name")
@org_option
@click.option("--roster", type=click.File("r"), default=None,
              help="one person per line (a repo each), or a NAME STUDENTS"
                   " table (a repo per row)")
@click.option("--from-canvas", is_flag=True,
              help="build the roster from canvas: one row per enrolled person")
@click.option("--canvas-group", default=None,
              help="with --from-canvas: one row per group in this canvas group set")
@click.option("--template", "template_url", default=None,
              help="REPO_URL whose content seeds this assignment's new repos")
@remove_unlisted_option
@click.option("--remove-dropped", "remove_dropped", is_flag=True, default=False,
              help="with --from-canvas: remove recorded rows no longer on the"
                   " canvas roster (their repos are left in place); the default"
                   " only warns about them")
@dryrun_option
def assignment_create(course, name, org, roster, from_canvas, canvas_group,
                      template_url, remove_unlisted, remove_dropped, dryrun):
    """Record assignment NAME in COURSE and create its repos.

    The roster comes from --roster or --from-canvas; running it again merges
    new rows in. --template alone records the starter repo without a roster.
    Only this assignment's repos are touched: its students are invited and
    the course's TAs team can read them. The rest of the course is left to
    sync.

    \b
    Examples:
      gh-class-sak assignment create CS-101 hw1 --from-canvas --apply
      gh-class-sak assignment create CS-101 project --from-canvas --canvas-group "Project Groups" --apply
      gh-class-sak assignment create CS-101 project --roster teams.tsv --apply
      gh-class-sak assignment create CS-101 hw2 --template https://github.com/cs101-fall/hw2-starter
    """
    if roster is not None and from_canvas:
        error("--from-canvas replaces --roster; pass one or the other")
        sys.exit(2)
    if roster is None and not from_canvas and not template_url:
        error("pass --roster FILE, --from-canvas to build the roster from"
              " canvas, or --template to record a starter repo alone")
        sys.exit(2)
    m._check_canvas_flags(from_canvas, canvas_group, remove_dropped)
    m._check_assignment_name(name)

    gh = get_github()
    m._assign(gh, *resolve_course(gh, course, org), course, roster, name,
              from_canvas, canvas_group, template_url, remove_unlisted,
              remove_dropped, dryrun, whole_classroom=False, parse=_parse_roster)


@gh_class_sak.command("sync")
@click.argument("course", required=False)
@org_option
@remove_unlisted_option
@dryrun_option
def sync(course, org, remove_unlisted, dryrun):
    """Make github match the recorded COURSE, or every course in --org.

    Creates missing repos, invites listed students, keeps the course's
    TAs team and branch protection in place. Collaborators the rows don't
    list are warned about; only --remove-unlisted-contributors revokes them
    (admins are never touched).

    \b
    Examples:
      gh-class-sak sync CS-101
      gh-class-sak sync CS-101 --apply
      gh-class-sak sync --org cs101-fall --apply
    """
    if not course and not org:
        error("pass a COURSE, or --org ORG to sync every course in it")
        sys.exit(2)
    gh = get_github()
    if course:
        org, classroom_dir = resolve_course(gh, course, org)
    else:
        org, classroom_dir = match_org(org, configured_orgs()) or org, None
    m._apply(gh, org, classroom_dir, course or org, remove_unlisted, dryrun)
