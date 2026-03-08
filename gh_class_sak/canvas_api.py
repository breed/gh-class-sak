from canvasapi import Canvas


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


_ENROLLMENT_QUERY = """
query ($courseId: ID!, $cursor: String) {
  course(id: $courseId) {
    enrollmentsConnection(first: 500, after: $cursor) {
      nodes {
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


def get_user_profile(canvas, user_id):
    return canvas.get_user(user_id).get_profile(include=["links"])
