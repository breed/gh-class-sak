from canvasapi import Canvas
from canvasapi.exceptions import Forbidden, ResourceDoesNotExist, Unauthorized


def get_canvas(config):
    url = config.get("CANVAS", "url", fallback=None)
    token = config.get("CANVAS", "token", fallback=None)
    if not url or not token:
        raise ValueError("missing url or token in [CANVAS] section")
    return Canvas(url, token)


def list_courses(canvas):
    teacher = list(canvas.get_courses(enrollment_type='teacher'))
    ta = list(canvas.get_courses(enrollment_type='ta'))
    seen = {c.id for c in teacher}
    return teacher + [c for c in ta if c.id not in seen]


def list_group_categories(course):
    return list(course.get_group_categories())


def list_groups_in_category(category):
    return list(category.get_groups())


def list_group_users(group):
    return list(group.get_users())


def send_message(canvas, user_id, subject, body):
    """send a canvas conversation message to one user.

    force_new so every run starts its own conversation instead of silently
    appending to an old thread the student may have muted.
    """
    canvas.create_conversation([str(user_id)], body, subject=subject,
                               force_new=True)


_ENROLLMENT_QUERY = """
query ($courseId: ID!, $cursor: String) {
  course(id: $courseId) {
    enrollmentsConnection(first: 500, after: $cursor) {
      nodes {
        type
        role {
          name
        }
        user {
          _id
          name
          email
        }
        courseSectionId
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


def graphql_enrollments(canvas, course_id):
    """Fetch all enrollments for a course via a single GraphQL query."""
    nodes = []
    cursor = None
    while True:
        result = canvas.graphql(_ENROLLMENT_QUERY,
                                {"courseId": str(course_id), "cursor": cursor})
        conn = result.get("data", {}).get("course", {}).get("enrollmentsConnection", {})
        nodes.extend(conn.get("nodes", []))
        page_info = conn.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break
    return nodes


_profile_cache = {}
# profiles canvas refused (a staff member's restricted profile, say), kept
# for the session like the good ones: asking again only gets the same "no",
# slowly, once per repo an audit looks at
_profile_failures = {}
_profile_failures_reported = set()
# canvas's lasting answers about one profile; only these are kept
PROFILE_REFUSALS = (Forbidden, Unauthorized, ResourceDoesNotExist)


def profile_cached(user_id):
    """whether the session already has an answer for this user's profile."""
    return user_id in _profile_cache or user_id in _profile_failures


def first_report_of_profile_failure(user_id):
    """True the first time a refused profile is reported this session."""
    if user_id in _profile_failures_reported:
        return False
    _profile_failures_reported.add(user_id)
    return True


def get_user_profile(course, user_id):
    """a user's profile (with links), reached through the course.

    the user object must come from the course — /courses/:id/users/:uid is
    open to teachers, while the account-scoped /users/:uid that
    Canvas.get_user() fetches is admin-or-self and 404s for everyone else.

    cached for the session: a roster consulted twice (rows, then email
    resolution) fetches each profile once. canvas user ids are global, so
    the cache keys on the id alone.
    """
    if user_id in _profile_failures:
        raise _profile_failures[user_id]
    if user_id not in _profile_cache:
        try:
            _profile_cache[user_id] = \
                course.get_user(user_id).get_profile(include=["links"])
        except PROFILE_REFUSALS as exc:
            # canvas said no for this profile: asking again only repeats it.
            # anything else (a timeout, an outage, a rate limit) is left
            # retryable, or a passing blip would strand the student
            _profile_failures[user_id] = exc
            raise
    return _profile_cache[user_id]
