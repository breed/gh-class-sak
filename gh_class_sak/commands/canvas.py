"""canvas-side actions: message the students who need to fix something.

repo access flows canvas profile -> github id -> repo invitation, and each
hop can strand a student: no github link, a link pointing at an account
that doesn't exist, or an invitation they never accepted. `canvas
message-missing` finds all three for an assignment and sends each stranded
student a canvas message saying exactly what to do.
"""

import sys

import click
from canvasapi.exceptions import CanvasException

from gh_class_sak.canvas_api import send_message
from gh_class_sak.commands.repos import (
    fetch_enrollment_data,
    resolve_assignment_repos,
    resolve_canvas_course,
)
from gh_class_sak.core import (
    config_ini,
    dryrun_option,
    error,
    get_github,
    gh_class_sak,
    has_canvas_config,
    output,
    progress,
    would,
)
from gh_class_sak.github_api import (
    get_github_user,
    pending_invitees,
    reserved_github_name,
    split_collaborators,
)

# the message sent per category. {name}, {login}, and {repo_url} are filled
# in per student; edit here to change what goes out.
MESSAGES = {
    "no-link": (
        "Action needed: add your GitHub account to your Canvas profile",
        """Hi {name},

This course manages assignment repositories on GitHub, and your GitHub
account is found through your Canvas profile — which has no GitHub link
yet, so you cannot be given access to your repository.

Please add it now:

1. Sign in to GitHub, or create a free account at https://github.com/signup
2. In Canvas, go to Account > Profile > Edit Profile
3. Under Links, add your GitHub profile URL: https://github.com/YOUR-USERNAME
4. Save

Once the link is in place you will receive a GitHub invitation to your
assignment repository. Reply here if you get stuck.""",
    ),
    "bad-link": (
        "Action needed: the GitHub link on your Canvas profile is broken",
        """Hi {name},

The GitHub link on your Canvas profile points to

    https://github.com/{login}

but no GitHub account named "{login}" exists — most likely a typo, or the
account was renamed or deleted. Until the link points to your real account
you cannot be given access to your assignment repository.

Please fix it:

1. Sign in to GitHub and open your own profile page; its address is the
   URL you need. It takes the form

       https://github.com/YOUR-USERNAME

2. In Canvas, go to Account > Profile > Edit Profile
3. Under Links, replace the old GitHub URL with the one you copied
4. Save

Reply here if you get stuck.""",
    ),
    "invited": (
        "Action needed: accept the invitation to your assignment repository",
        """Hi {name},

A GitHub invitation to your assignment repository

    {repo_url}

was sent to you, but it has not been accepted, so you cannot push your
work yet. Sign in to GitHub as "{login}" and open

    {repo_url}/invitations

or use the invitation email GitHub sent to your account's address. GitHub
invitations expire after 7 days — if yours has expired, reply here and a
new one will be sent.

Note: if following the link shows a 404 page, you are not logged in to
GitHub (or are logged in to a different account). Log in as "{login}" and
try the link again.""",
    ),
}

_FOOTER = "\n\n**You DO NOT need to respond to this email." \
          " It is for your information.**"
# every message carries the same closing line
MESSAGES = {category: (subject, body + _FOOTER)
            for category, (subject, body) in MESSAGES.items()}


@gh_class_sak.group("canvas")
def canvas_group():
    """Canvas-side actions: message students who need to fix something."""
    pass


@canvas_group.command("message-missing")
@click.argument("classroom")
@click.argument("assignment")
@dryrun_option
def message_missing(classroom, assignment, dryrun):
    """Message each student stranded on the way to their assignment repo.

    Three categories, one canvas message each: no GitHub link on the Canvas
    profile, a link pointing at a GitHub account that doesn't exist, and a
    repo invitation that was never accepted. Students already collaborating
    are left alone; one with a working account but neither access nor an
    invitation is an error aimed at you (exit 1) — the fix is meta apply,
    not a message. A dry run lists who would get what and prints the full
    message texts.
    """
    if not has_canvas_config():
        error(f"this command needs a [CANVAS] section in {config_ini}")
        sys.exit(2)
    gh = get_github()
    room, found = resolve_assignment_repos(classroom, assignment)
    canvas_ctx = resolve_canvas_course(room)
    enrollment = fetch_enrollment_data(room, canvas_ctx, resolve_students=True)

    # who already reaches github, and who is stuck at a pending invitation
    collaborators = set()
    invited_repo = {}
    for _team, repo in progress(found, "checking repo invitations"):
        members, admins = split_collaborators(repo)
        collaborators.update(u.login.lower() for u in members + admins)
        for login in pending_invitees(repo):
            invited_repo.setdefault(login.lower(), repo)

    todo = []  # (student, category, extra format args)
    stranded = []  # error lines, held to the end: an error mid-loop would
    # be torn apart by the progress bar and scroll out of sight
    for student in progress(enrollment["students"], "checking github accounts"):
        login = student.get("github")
        if not login:
            todo.append((student, "no-link", {}))
        elif login.lower() in collaborators:
            continue
        elif login.lower() in invited_repo:
            todo.append((student, "invited",
                         {"login": login,
                          "repo_url": invited_repo[login.lower()].html_url}))
        elif reserved_github_name(login) or get_github_user(gh, login) is None:
            # a github route (github.com/dashboard) is bad without asking
            todo.append((student, "bad-link", {"login": login}))
        else:
            # a working link but no access and no invitation: nothing the
            # student can act on, so the error goes to the instructor
            stranded.append(
                f'{student["name"]} ({login}) is not a collaborator on any'
                " repo for this assignment and has no pending invitation"
                " — run: meta apply")

    if not todo and not stranded:
        output("nothing to do")
        return

    canvas, _course = canvas_ctx
    # no bar for a dry run: nothing slow happens, the would-lines are the point
    recipients = todo if dryrun else progress(todo, "sending canvas messages")
    for student, category, extra in recipients:
        subject, body = MESSAGES[category]
        line = (f'message {student["name"]} <{student["email"] or "-"}>'
                f" ({category}): {subject}")
        if dryrun:
            would(f"would {line}")
            continue
        try:
            send_message(canvas, student["id"], subject,
                         body.format(name=student["name"], **extra))
        except CanvasException as exc:
            # one refused recipient must not abort the rest of the sends
            stranded.append(f'cannot message {student["name"]}'
                            f' <{student["email"] or "-"}>: {exc}')
            continue
        output(line)

    if dryrun:
        # show exactly what would go out, once per category that has anyone
        for category in ("no-link", "bad-link", "invited"):
            if any(c == category for _s, c, _e in todo):
                subject, body = MESSAGES[category]
                output("")
                output(f"--- {category}: {subject} ---")
                output(body)
    if stranded:
        for message in stranded:
            error(message)
        sys.exit(1)
