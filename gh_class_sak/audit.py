"""The audit trail: what the tool changed on github, and why.

Every real change to who can reach a repo — a repo created or adopted, an
invitation sent, a collaborator revoked, an invitation cancelled, a TA
added to or removed from the TAs team — is recorded with the reason the
tool had for it: the tsv row and identity it came from, and whether the
github id was read off a canvas profile link. A run appends its entries to
each course's audit.log in the classroom-meta repo, committed with the
rest of the run, so the history can't be quietly rewritten.

The file is tab-separated but named .log, not .tsv: every .tsv in a course
directory is an assignment.
"""

import os
from datetime import datetime, timezone

import click

LOG_NAME = "audit.log"
HEADERS = ("TIME", "BY", "COMMAND", "ACTION", "REPO", "WHO", "WHY")

_pending = []  # (course dir, [field, ...]) recorded but not yet written


def reset():
    """forget anything unwritten; each invocation starts clean."""
    _pending.clear()


def record(course_dir, action, repo, who, why):
    """note one change the running command just made."""
    ctx = click.get_current_context(silent=True)
    command = ctx.command_path if ctx else "-"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _pending.append((course_dir, [when, None, command, action, repo, who, why]))


def flush(checkout, by):
    """append the recorded changes to each course's audit.log in the checkout.

    by is who ran the command (the token's login). returns True when
    anything was written, so the caller knows to commit. a course whose
    directory is gone (deleted this run) has nowhere to log to.
    """
    if not _pending:
        return False
    per_course = {}
    for course_dir, fields in _pending:
        per_course.setdefault(course_dir, []).append(fields)
    _pending.clear()
    wrote = False
    for course_dir, entries in per_course.items():
        directory = os.path.join(checkout, course_dir)
        if not os.path.isdir(directory):
            continue
        path = os.path.join(directory, LOG_NAME)
        new = not os.path.exists(path)
        with open(path, "a") as f:
            if new:
                f.write("\t".join(HEADERS) + "\n")
            for fields in entries:
                fields[1] = by
                f.write("\t".join(_cell(value) for value in fields) + "\n")
        wrote = True
    return wrote


def _cell(value):
    """one field: never empty, never breaking the tab-separated line."""
    text = str(value) if value else "-"
    return text.replace("\t", " ").replace("\n", " ")
