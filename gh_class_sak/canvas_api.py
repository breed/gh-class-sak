from gh_class_sak.core import paginate


def list_courses(session, base_url):
    teacher = paginate(session, f"{base_url}/api/v1/courses?enrollment_type=teacher")
    ta = paginate(session, f"{base_url}/api/v1/courses?enrollment_type=ta")
    seen = {c["id"] for c in teacher}
    return teacher + [c for c in ta if c["id"] not in seen]


def list_group_categories(session, base_url, course_id):
    url = f"{base_url}/api/v1/courses/{course_id}/group_categories"
    return paginate(session, url)


def list_groups_in_category(session, base_url, category_id):
    url = f"{base_url}/api/v1/group_categories/{category_id}/groups"
    return paginate(session, url)


def list_group_users(session, base_url, group_id):
    url = f"{base_url}/api/v1/groups/{group_id}/users"
    return paginate(session, url)
