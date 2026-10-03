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
_bound = {}  # the running command's meta checkout and github client


def reset():
    """forget anything unwritten; each invocation starts clean."""
    _pending.clear()
    _bound.clear()


def bind(checkout, gh):
    """the meta checkout this command's entries belong in, so they can be
    saved even if the command stops early."""
    _bound.update(checkout=checkout, gh=gh)


def record(course_dir, action, repo, who, why):
    """note one change the running command just made."""
    ctx = click.get_current_context(silent=True)
    command = ctx.command_path if ctx else "-"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if ctx and not _bound.get("hooked"):
        # a change that happened must be logged even when the command
        # fails after it: the normal end-of-run flush never comes then
        ctx.call_on_close(_save_what_happened)
        _bound["hooked"] = True
    _pending.append((course_dir, [when, None, command, action, repo, who, why]))


def _save_what_happened():
    """a command ended with entries still unwritten — it stopped early.
    commit just the audit logs: the run's other half-done edits to the
    meta checkout are not committed. if even that fails, print the
    entries so the record isn't lost."""
    if not _pending:
        return
    from gh_class_sak import meta_store as ms
    from gh_class_sak.core import get_token, warn
    from gh_class_sak.github_api import token_login

    entries = list(_pending)
    checkout = _bound.get("checkout")
    try:
        if checkout is None:
            raise RuntimeError("no classroom-meta checkout")
        gh = _bound.get("gh")
        paths = flush(checkout, (token_login(gh) if gh else None) or "-")
        if paths:
            ms.commit_paths_and_push(checkout, paths,
                                     "audit (the run stopped early)", get_token())
    except Exception as exc:  # the record must survive any failure here
        warn(f"could not save the audit log ({exc}); these changes happened:")
        for course_dir, fields in entries:
            warn("  " + "\t".join([course_dir] + [_cell(value) for value in fields]))


def flush(checkout, by):
    """append the recorded changes to each course's audit.log in the checkout.

    by is who ran the command (the token's login). returns the paths
    written — empty when there was nothing to write — so the caller knows
    whether to commit. a course whose directory is gone (deleted this run)
    has nowhere to log to.
    """
    if not _pending:
        return []
    per_course = {}
    for course_dir, fields in _pending:
        per_course.setdefault(course_dir, []).append(fields)
    _pending.clear()
    wrote = []
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
        wrote.append(os.path.join(course_dir, LOG_NAME))
    return wrote


def _cell(value):
    """one field: never empty, never breaking the tab-separated line."""
    text = str(value) if value else "-"
    return text.replace("\t", " ").replace("\n", " ")
