import os

import pytest
from git import Repo as GitRepo

from gh_class_sak import meta_store as ms
from tests.fakes import FakeGithub, FakeOrg, FakeRepo

ORG = "SJSU-CMPE-195"


class TestClassroomIni:
    def test_round_trip_with_template(self):
        text = ms.serialize_classroom_ini("sp26-project", "ORG/Template")
        assert ms.parse_classroom_ini(text) == {
            "prefix": "sp26-project", "template": "ORG/Template",
            "canvas_course": None, "protection": None,
            "linear_history": None, "force_push": None,
            "tas": [], "templates": {}, "group_sets": {},
        }

    def test_round_trip_with_tas_and_templates(self):
        text = ms.serialize_classroom_ini(
            "p", tas=["ta-alice@sjsu.edu/ta-alice", "/prof-lee"],
            templates={"hw1": "https://github.com/org/hw1-starter.git"})
        parsed = ms.parse_classroom_ini(text)
        assert parsed["tas"] == ["ta-alice@sjsu.edu/ta-alice", "/prof-lee"]
        assert parsed["templates"] == {
            "hw1": "https://github.com/org/hw1-starter.git"}
        assert ms.serialize_classroom_ini(**parsed) == text

    def test_round_trip_with_canvas_course_and_group_sets(self):
        text = ms.serialize_classroom_ini(
            "p", canvas_course="CMPE-195A",
            group_sets={"project": "Project Groups", "hw1": "HW Pairs"})
        parsed = ms.parse_classroom_ini(text)
        assert parsed["canvas_course"] == "CMPE-195A"
        assert parsed["group_sets"] == {"project": "Project Groups",
                                        "hw1": "HW Pairs"}
        assert ms.serialize_classroom_ini(**parsed) == text

    def test_round_trip_without_template(self):
        text = ms.serialize_classroom_ini("sp26-project")
        parsed = ms.parse_classroom_ini(text)
        assert parsed["prefix"] == "sp26-project"
        assert parsed["template"] is None

    def test_round_trip_with_repo_settings(self):
        text = ms.serialize_classroom_ini("p", protection="pr-review",
                                          linear_history=False, force_push=True)
        parsed = ms.parse_classroom_ini(text)
        assert parsed["protection"] == "pr-review"
        assert parsed["linear_history"] is False
        assert parsed["force_push"] is True

    def test_absent_settings_are_not_written_back(self):
        text = "[CLASSROOM]\nprefix = p\n"
        assert ms.serialize_classroom_ini(**ms.parse_classroom_ini(text)) == text

    def test_serialize_without_prefix_omits_the_line(self):
        text = ms.serialize_classroom_ini()
        assert text == "[CLASSROOM]\n"
        assert ms.parse_classroom_ini(text)["prefix"] is None

    def test_bad_protection_value_raises(self):
        with pytest.raises(ValueError, match="protection"):
            ms.parse_classroom_ini("[CLASSROOM]\nprefix = p\nprotection = review\n")

    def test_bad_boolean_raises(self):
        with pytest.raises(ValueError, match="linear_history"):
            ms.parse_classroom_ini("[CLASSROOM]\nprefix = p\nlinear_history = maybe\n")

    def test_effective_repo_settings_defaults(self):
        parsed = ms.parse_classroom_ini("[CLASSROOM]\nprefix = p\n")
        assert ms.effective_repo_settings(parsed) == ("none", True, False)

    def test_effective_repo_settings_passes_explicit_values(self):
        parsed = ms.parse_classroom_ini(
            "[CLASSROOM]\nprefix = p\nprotection = pr-review\n"
            "linear_history = false\nforce_push = true\n")
        assert ms.effective_repo_settings(parsed) == ("pr-review", False, True)


class TestTas:
    def test_ignores_blanks_and_comments(self):
        text = "# graders\nta-one\n\ngrader@sjsu.edu  # resolves later\n"
        assert ms.parse_tas(text) == ["ta-one", "grader@sjsu.edu"]

    def test_identity_entries_parse(self):
        text = "ta-alice@sjsu.edu/ta-alice\n/prof-lee\n"
        assert ms.parse_tas(text) == ["ta-alice@sjsu.edu/ta-alice", "/prof-lee"]


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


class TestIdentitySyntax:
    def test_both_halves(self):
        assert ms.parse_identity("joe@example.com/JoeDev") \
            == ("joe@example.com", "JoeDev")

    def test_email_only(self):
        assert ms.parse_identity("joe@example.com/") == ("joe@example.com", None)

    def test_github_only(self):
        assert ms.parse_identity("/JoeDev") == (None, "JoeDev")

    def test_legacy_entries_still_parse(self):
        assert ms.parse_identity("joe@example.com") == ("joe@example.com", None)
        assert ms.parse_identity("JoeDev") == (None, "JoeDev")

    def test_format_round_trips(self):
        for email, github in (("joe@example.com", "JoeDev"),
                              ("joe@example.com", None), (None, "JoeDev")):
            assert ms.parse_identity(ms.format_identity(email, github)) \
                == (email, github)


class TestJoinRepoName:
    def test_joins_the_parts_with_dashes(self):
        assert ms.join_repo_name("sp26-195a", "hw1", "team-1") == "sp26-195a-hw1-team-1"

    def test_an_unset_prefix_drops_its_segment(self):
        assert ms.join_repo_name(None, "hw1", "team-1") == "hw1-team-1"
        assert ms.join_repo_name("", "hw1", "team-1") == "hw1-team-1"


@pytest.fixture
def bare_origin(tmp_path):
    origin = tmp_path / "classroom-meta.git"
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
        ms.save_classroom(checkout, "cs101", "prefix-a", "ORG/Tpl",
                       tas=["ta-one"],
                       assignments={"hw1": [{"name": "t1", "students": ["a"],
                                             "repo": None, "repo_id": None}]})
        assert ms.commit_and_push(checkout, "seed") is True

        # a "second machine" sees the pushed state
        other = ms.checkout_meta(str(bare_origin), "other-checkout")
        course = ms.load_classroom(other, "cs101")
        assert course["prefix"] == "prefix-a"
        assert course["template"] == "ORG/Tpl"
        assert course["tas"] == ["ta-one"]
        assert course["assignments"]["hw1"][0]["name"] == "t1"

    def test_load_classroom_collects_every_tsv_sorted(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        row = {"name": "t1", "students": [], "repo": None, "repo_id": None}
        ms.save_classroom(checkout, "cs101", "p",
                          assignments={"project": [row], "hw1": [row]})
        course = ms.load_classroom(checkout, "cs101")
        assert list(course["assignments"]) == ["hw1", "project"]

    def test_save_classroom_writes_only_named_assignments(self, bare_origin,
                                                          checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        row = {"name": "t1", "students": [], "repo": None, "repo_id": None}
        ms.save_classroom(checkout, "cs101", "p",
                          assignments={"hw1": [row], "project": [row]})
        other = {"name": "t2", "students": ["b"], "repo": None, "repo_id": None}
        ms.save_classroom(checkout, "cs101", "p", assignments={"hw1": [other]})
        course = ms.load_classroom(checkout, "cs101")
        assert course["assignments"]["hw1"][0]["name"] == "t2"
        assert course["assignments"]["project"][0]["name"] == "t1"

    def test_classroom_without_tsvs_has_no_assignments(self, bare_origin,
                                                       checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p")
        assert ms.load_classroom(checkout, "cs101")["assignments"] == {}

    def test_legacy_tas_file_still_reads(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p")
        with open(os.path.join(checkout, "cs101", "tas"), "w") as f:
            f.write("/ta-alice\n")
        assert ms.load_classroom(checkout, "cs101")["tas"] == ["/ta-alice"]

    def test_save_moves_the_tas_into_the_ini(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p")
        legacy = os.path.join(checkout, "cs101", "tas")
        with open(legacy, "w") as f:
            f.write("/ta-alice\n")
        data = ms.load_classroom(checkout, "cs101")
        ms.save_classroom(checkout, "cs101", "p", tas=data["tas"])
        assert not os.path.exists(legacy)
        assert ms.load_classroom(checkout, "cs101")["tas"] == ["/ta-alice"]

    def test_students_tsv_is_just_an_assignment_named_students(self, bare_origin,
                                                               checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p")
        with open(os.path.join(checkout, "cs101", "students.tsv"), "w") as f:
            f.write("t1 a\n")
        course = ms.load_classroom(checkout, "cs101")
        assert list(course["assignments"]) == ["students"]

    def test_push_is_a_no_op_when_clean(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p")
        assert ms.commit_and_push(checkout, "seed") is True
        assert ms.commit_and_push(checkout, "again") is False

    def test_checkout_twice_fast_forwards(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p")
        ms.commit_and_push(checkout, "seed")
        assert ms.checkout_meta(str(bare_origin), ORG) == checkout

    def test_list_classrooms_lists_only_classroom_dirs(self, bare_origin, checkout_root):
        checkout = ms.checkout_meta(str(bare_origin), ORG)
        ms.save_classroom(checkout, "cs101", "p1")
        ms.save_classroom(checkout, "cs210", "p2")
        assert ms.list_classrooms(checkout) == ["cs101", "cs210"]


class TestLoadMetaCourses:
    def test_returns_empty_without_a_meta_repo(self, checkout_root):
        gh = FakeGithub(orgs=[FakeOrg(ORG)])
        assert ms.load_meta_classrooms(gh, ORG) == {}

    def test_loads_courses_through_a_real_clone(self, bare_origin, checkout_root):
        seed = ms.checkout_meta(str(bare_origin), "seeding")
        ms.save_classroom(seed, "cs101", "prefix-a", tas=["ta-one"])
        ms.commit_and_push(seed, "seed")

        meta_repo = FakeRepo(ORG, "classroom-meta", clone_url=str(bare_origin))
        gh = FakeGithub(orgs=[FakeOrg(ORG, [meta_repo])])
        courses = ms.load_meta_classrooms(gh, ORG)
        assert list(courses) == ["cs101"]
        assert courses["cs101"]["prefix"] == "prefix-a"

    def test_bad_classroom_ini_is_skipped_with_a_warning(self, bare_origin,
                                                         checkout_root, capsys):
        seed = ms.checkout_meta(str(bare_origin), "seeding")
        ms.save_classroom(seed, "cs101", "prefix-a")
        bad = os.path.join(seed, "cs210")
        os.makedirs(bad)
        with open(os.path.join(bad, "classroom.ini"), "w") as f:
            f.write("[CLASSROOM]\nprefix = p\nprotection = review\n")
        ms.commit_and_push(seed, "seed")

        meta_repo = FakeRepo(ORG, "classroom-meta", clone_url=str(bare_origin))
        gh = FakeGithub(orgs=[FakeOrg(ORG, [meta_repo])])
        classrooms = ms.load_meta_classrooms(gh, ORG)
        assert list(classrooms) == ["cs101"]
        assert "cs210" in capsys.readouterr().err
