from configparser import ConfigParser

import pytest

from gh_class_sak import canvas_api

URL = "https://canvas.example.edu"


def config(**canvas):
    parser = ConfigParser(interpolation=None)
    parser["CANVAS"] = canvas
    return parser


@pytest.fixture
def made(monkeypatch):
    """the (url, token) get_canvas builds its client with — no network."""
    calls = []
    monkeypatch.setattr(canvas_api, "Canvas",
                        lambda url, token: calls.append((url, token)))
    return calls


class TestGetCanvas:
    def test_token_from_config(self, made):
        canvas_api.get_canvas(config(url=URL, token="from-config"))
        assert made == [(URL, "from-config")]

    def test_env_token_beats_config(self, made, monkeypatch):
        monkeypatch.setenv("CANVAS_API_TOKEN", "from-env")
        canvas_api.get_canvas(config(url=URL, token="from-config"))
        assert made == [(URL, "from-env")]

    def test_env_token_without_one_in_config(self, made, monkeypatch):
        monkeypatch.setenv("CANVAS_API_TOKEN", "from-env")
        canvas_api.get_canvas(config(url=URL))
        assert made == [(URL, "from-env")]

    def test_empty_env_falls_back_to_config(self, made, monkeypatch):
        monkeypatch.setenv("CANVAS_API_TOKEN", "")
        canvas_api.get_canvas(config(url=URL, token="from-config"))
        assert made == [(URL, "from-config")]

    def test_no_token_anywhere_names_both_places(self, made):
        with pytest.raises(ValueError, match="CANVAS_API_TOKEN.*\\[CANVAS\\]"):
            canvas_api.get_canvas(config(url=URL))
        assert made == []

    def test_missing_url(self, made, monkeypatch):
        monkeypatch.setenv("CANVAS_API_TOKEN", "from-env")
        with pytest.raises(ValueError, match="missing url"):
            canvas_api.get_canvas(config(token="from-config"))
        assert made == []
