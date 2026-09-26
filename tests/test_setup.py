import os

from gh_class_sak.commands import setup as setup_cmd
from tests.conftest import ORG, run


def with_token(monkeypatch, found=True):
    probe = ("ghp_faketoken", "GH_TOKEN environment variable") if found \
        else (None, None)
    monkeypatch.setattr(setup_cmd, "probe_token", lambda: probe)


class TestHelpMeSetup:
    def test_everything_good(self, cli, config_file, fake_canvas, monkeypatch):
        with_token(monkeypatch)
        monkeypatch.setattr(setup_cmd, "canvas_client", lambda config: fake_canvas)
        result = run(cli, "help-me-setup")
        assert result.exit_code == 0, result.output
        assert "github token   found" in result.output
        assert f"[ORGS]         {ORG}" in result.output
        assert "classroom-meta ok — cmpe_195a" in result.output
        assert "[CANVAS]       ok" in result.output
        assert "everything looks good" in result.output

    def test_missing_config_explains_how_to_create_one(self, cli, no_config,
                                                       monkeypatch):
        with_token(monkeypatch)
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert "create it with content like" in result.output
        assert "[ORGS]" in result.output
        assert "one github org per line" in result.output
        assert "[CANVAS]" in result.output
        assert "needs attention: config file" in result.output

    def test_missing_token_is_reported_with_an_example(self, cli, config_file,
                                                       fake_canvas, monkeypatch):
        with_token(monkeypatch, found=False)
        monkeypatch.setattr(setup_cmd, "canvas_client", lambda config: fake_canvas)
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert "github token   not found" in result.output
        assert "gh auth login" in result.output
        assert "export GH_TOKEN=" in result.output

    def test_empty_orgs_section_shows_an_example(self, cli, tmp_path, monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        path = tmp_path / "cfg.ini"
        path.write_text("[ORGS]\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert "no orgs listed" in result.output
        assert "your-github-org" in result.output

    def test_incomplete_canvas_section_shows_an_example(self, cli, tmp_path,
                                                        monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        path = tmp_path / "cfg.ini"
        path.write_text(f"[ORGS]\n{ORG}\n\n[CANVAS]\nurl = u\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert "missing url or token" in result.output
        assert "token = YOUR_CANVAS_API_TOKEN" in result.output

    def test_org_without_classroom_meta_is_flagged(self, cli, config_file,
                                                   fake_github, fake_canvas,
                                                   monkeypatch):
        with_token(monkeypatch)
        monkeypatch.setattr(setup_cmd, "canvas_client", lambda config: fake_canvas)
        org = fake_github.get_organization(ORG)
        org._repos[:] = [r for r in org._repos if r.name != "classroom-meta"]
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert "no classroom-meta repo" in result.output
        assert f"gh-class-sak course init YOUR-COURSE --org {ORG}" in result.output
        assert "migrate-github-classroom" in result.output

    def test_canvas_is_optional(self, cli, tmp_path, monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        path = tmp_path / "cfg.ini"
        path.write_text(f"[ORGS]\n{ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(cli, "help-me-setup")
        assert result.exit_code == 0, result.output
        assert "[CANVAS]       not configured (optional" in result.output
        assert "to enable the roster features, add:" in result.output
        assert "url = https://your-canvas-instance.instructure.com" in result.output

    def test_unreachable_org_is_reported(self, cli, tmp_path, monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        path = tmp_path / "cfg.ini"
        path.write_text("[ORGS]\nno-such-org\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert "no-such-org: not reachable" in result.output


class TestCreateConfig:
    def canvas_ok(self, monkeypatch, fake_canvas):
        monkeypatch.setattr(setup_cmd, "canvas_client", lambda config: fake_canvas)

    def test_writes_orgs_and_canvas(self, cli, no_config, fake_canvas, monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        self.canvas_ok(monkeypatch, fake_canvas)
        result = run(cli, "help-me-setup", "--create-config",
                     input=f"{ORG}\nhttps://canvas.example.edu\nxyz\n")
        assert result.exit_code == 0, result.output
        text = open(core.config_ini).read()
        assert f"[ORGS]\n{ORG}\n" in text
        assert "[CANVAS]\nurl = https://canvas.example.edu\ntoken = xyz\n" in text
        if os.name == "posix":  # the canvas token is a secret
            assert os.stat(core.config_ini).st_mode & 0o077 == 0
        assert f"wrote {core.config_ini}" in result.output
        # and then the check runs against the new file
        assert "everything looks good" in result.output

    def test_canvas_is_optional(self, cli, no_config, monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        result = run(cli, "help-me-setup", "--create-config", input=f"{ORG}\n\n")
        assert "[CANVAS]" not in open(core.config_ini).read()
        assert f"[ORGS]         {ORG}" in result.output

    def test_an_existing_config_is_only_filled_in(self, cli, tmp_path, fake_canvas,
                                                  monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        self.canvas_ok(monkeypatch, fake_canvas)
        path = tmp_path / "cfg.ini"
        path.write_text(f"# mine\n[ORGS]\n{ORG}\n")
        monkeypatch.setattr(core, "config_ini", str(path))
        result = run(cli, "help-me-setup", "--create-config",
                     input="https://canvas.example.edu\nxyz\n")
        assert result.exit_code == 0, result.output
        assert path.read_text() == (f"# mine\n[ORGS]\n{ORG}\n\n[CANVAS]\n"
                                    "url = https://canvas.example.edu\ntoken = xyz\n")

    def test_a_complete_config_is_left_alone(self, cli, config_file, fake_canvas,
                                             monkeypatch):
        with_token(monkeypatch)
        self.canvas_ok(monkeypatch, fake_canvas)
        before = open(config_file).read()
        result = run(cli, "help-me-setup", "--create-config")
        assert result.exit_code == 0, result.output
        assert "already has [ORGS] and [CANVAS]" in result.output
        assert open(config_file).read() == before

    def test_the_missing_config_message_offers_the_flag(self, cli, no_config,
                                                        monkeypatch):
        with_token(monkeypatch)
        result = run(cli, "help-me-setup")
        assert "gh-class-sak help-me-setup --create-config" in result.output

    def test_at_a_terminal_it_offers_to_write_the_file(self, cli, no_config,
                                                        monkeypatch):
        from gh_class_sak import core
        with_token(monkeypatch)
        monkeypatch.setattr(setup_cmd, "_can_ask", lambda: True)
        run(cli, "help-me-setup", input=f"y\n{ORG}\n\n")
        assert f"[ORGS]\n{ORG}\n" in open(core.config_ini).read()


class TestTokenScope:
    def test_a_token_without_repo_scope_gets_the_fix(self, cli, config_file,
                                                     fake_github, fake_canvas,
                                                     monkeypatch):
        with_token(monkeypatch)
        monkeypatch.setattr(setup_cmd, "canvas_client", lambda config: fake_canvas)
        fake_github.oauth_scopes = ["read:org"]
        result = run(cli, "help-me-setup")
        assert result.exit_code == 1
        assert 'lacks the "repo" scope' in result.output
        assert "gh auth refresh -h github.com -s repo" in result.output
        assert "needs attention: token scope" in result.output


def test_a_good_setup_mentions_tab_completion(cli, config_file, fake_canvas,
                                              monkeypatch):
    with_token(monkeypatch)
    monkeypatch.setattr(setup_cmd, "canvas_client", lambda config: fake_canvas)
    result = run(cli, "help-me-setup")
    assert result.exit_code == 0, result.output
    assert "tip: tab-completion — gh-class-sak completion --help" in result.output
