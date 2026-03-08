import click

from gh_class_sak.core import gh_class_sak, get_session, output, error
from gh_class_sak.github_api import list_classrooms, list_assignments


@gh_class_sak.command()
def classrooms():
    """List classrooms and their assignments."""
    session = get_session()
    rooms = list_classrooms(session)
    if not rooms:
        error("no classrooms found")
        return
    for room in rooms:
        assignments = list_assignments(session, room["id"])
        if not assignments:
            output(f"{room['name']}: (no assignments)")
        else:
            for a in assignments:
                output(f"{room['name']}: {a['title']}")
