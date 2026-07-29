import pytest
from git import Repo as GitRepo

from gh_class_sak import meta_store as ms
from tests.fakes import FakeGithub, FakeOrg, FakeRepo

ORG = "SJSU-CMPE-195"


class TestCourseIni:
    def test_round_trip_with_template(self):
        text = ms.serialize_course_ini("sp26-project", "ORG/Template")
        assert ms.parse_course_ini(text) == ("sp26-project", "ORG/Template")

    def test_round_trip_without_template(self):
        text = ms.serialize_course_ini("sp26-project")
        assert ms.parse_course_ini(text) == ("sp26-project", None)


class TestTas:
    def test_ignores_blanks_and_comments(self):
        text = "# graders\nta-one\n\ngrader@sjsu.edu  # resolves later\n"
        assert ms.parse_tas(text) == ["ta-one", "grader@sjsu.edu"]

    def test_round_trip(self):
        entries = ["ta-one", "grader@sjsu.edu"]
        assert ms.parse_tas(ms.serialize_tas(entries)) == entries


class TestStudentsTsv:
    def test_parses_the_two_column_instructor_table(self):
        rows = ms.parse_students_tsv(
            "NAME  STUDENTS\n"
            "team-1  jane@sjsu.edu,msmith\n"
            "solo    rpatel\n"
        )
        assert rows == [
            {"name": "team-1", "students": ["jane@sjsu.edu", "msmith"],
             "repo": None, "repo_id": None},
            {"name": "solo", "students": ["rpatel"], "repo": None, "repo_id": None},
        ]

    def test_full_round_trip(self):
        rows = [
            {"name": "team-1", "students": ["jdoe", "msmith"],
             "repo": "https://github.com/o/p-team-1", "repo_id": 912345},
            {"name": "solo", "students": ["rpatel"], "repo": None, "repo_id": None},
        ]
        assert ms.parse_students_tsv(ms.serialize_students_tsv(rows)) == rows

    def test_header_and_comments_are_ignored(self):
        rows = ms.parse_students_tsv("# a note\nNAME STUDENTS REPO REPO_ID\n\nx a,b\n")
        assert [r["name"] for r in rows] == ["x"]


class TestMergeRows:
    EXISTING = [{"name": "team-1", "students": ["jdoe"],
                 "repo": "https://github.com/o/p-team-1", "repo_id": 42}]

    def test_appends_new_names(self):
        merged, changed = ms.merge_rows(self.EXISTING,
                                        [{"name": "new", "students": ["x"],
                                          "repo": None, "repo_id": None}])
        assert [r["name"] for r in merged] == ["team-1", "new"]
        assert changed == ["new"]

    def test_updates_students_but_never_the_recorded_repo(self):
        merged, changed = ms.merge_rows(self.EXISTING,
                                        [{"name": "team-1", "students": ["jdoe", "late-add"],
                                          "repo": None, "repo_id": None}])
        assert merged[0]["students"] == ["jdoe", "late-add"]
        assert merged[0]["repo_id"] == 42
        assert changed == ["team-1"]

    def test_identical_input_changes_nothing(self):
        merged, changed = ms.merge_rows(self.EXISTING,
                                        [{"name": "team-1", "students": ["jdoe"],
                                          "repo": None, "repo_id": None}])
        assert changed == []
        assert merged == self.EXISTING


@pytest.fixture
def bare_origin(tmp_path):
    origin = tmp_path / "meta.git"
    GitRepo.init(origin, bare=True)
    return origin


@pytest.fixture
def checkout_root(tmp_path, monkeypatch):
    root = tmp_path / "checkouts"
    monkeypatch.setattr(ms, "meta_checkout_dir", lambda org: str(root / org))
    return root


class TestGitPlumbing:
    def test_full_cycle_against_a_local_origin(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_course(checkout, "cs101", "prefix-a", "ORG/Tpl",
                       tas=["ta-one"], rows=[{"name": "t1", "students": ["a"],
                                              "repo": None, "repo_id": None}])
        assert ms.commit_and_push(checkout, "seed") is True

        # a "second machine" sees the pushed state
        other = ms.checkout_meta(str(bare_origin), "other-checkout")
        course = ms.load_course(other, "cs101")
        assert course["prefix"] == "prefix-a"
        assert course["template"] == "ORG/Tpl"
        assert course["tas"] == ["ta-one"]
        assert course["rows"][0]["name"] == "t1"

    def test_push_is_a_no_op_when_clean(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_course(checkout, "cs101", "p")
        assert ms.commit_and_push(checkout, "seed") is True
        assert ms.commit_and_push(checkout, "again") is False

    def test_checkout_twice_fast_forwards(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_course(checkout, "cs101", "p")
        ms.commit_and_push(checkout, "seed")
        assert ms.checkout_meta(str(bare_origin), ORG) == checkout

    def test_load_courses_lists_only_course_dirs(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_course(checkout, "cs101", "p1")
        ms.save_course(checkout, "cs210", "p2")
        assert ms.list_courses(checkout) == ["cs101", "cs210"]


class TestLoadMetaCourses:
    def test_returns_empty_without_a_meta_repo(self, checkout_root):
        gh = FakeGithub(orgs=[FakeOrg(ORG)])
        assert ms.load_meta_courses(gh, ORG) == {}

    def test_loads_courses_through_a_real_clone(self, bare_origin, checkout_root):
        seed = ms.checkout_meta(str(bare_origin), "seeding")
        ms.save_course(seed, "cs101", "prefix-a", tas=["ta-one"])
        ms.commit_and_push(seed, "seed")

        meta_repo = FakeRepo(ORG, "meta", clone_url=str(bare_origin))
        gh = FakeGithub(orgs=[FakeOrg(ORG, [meta_repo])])
        courses = ms.load_meta_courses(gh, ORG)
        assert list(courses) == ["cs101"]
        assert courses["cs101"]["prefix"] == "prefix-a"
