"""The course-centered commands: course, assignment create, and sync.

A COURSE argument is always a course, never an org; --org names the org
when it can't be inferred. The work itself is shared with the meta
commands these replace.
"""
import sys

import click

from gh_class_sak.commands import meta as m
from gh_class_sak.core import (
    config_ini,
    configured_orgs,
    dryrun_option,
    error,
    get_github,
    gh_class_sak,
    match_org,
    resolve_course,
)

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


@gh_class_sak.group("course")
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
@dryrun_option
def course_init(course, org, prefix, template, canvas_course, dryrun):
    """Record a new COURSE, creating the org's classroom-meta repo if needed."""
    m._init(course, org, prefix, template, canvas_course, dryrun)


@course_group.command("list")
@click.argument("course", required=False)
@org_option
def course_list(course, org):
    """List the recorded courses: prefix, TA count, and assignments.

    Without COURSE, every course in --org (or every configured org) is listed.
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
    """Show a course's recorded state, checked against the live org."""
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
    """
    gh = get_github()
    m._delete(gh, *resolve_course(gh, course, org), course, delete_repo, dryrun)


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
              help="a NAME + STUDENTS table: one row per repo")
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
              remove_dropped, dryrun, whole_classroom=False)


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
