"""messages printed under a progress bar: flashed on the bar line, cleared
by the next update, and replayed for real when the bar finishes."""
import io
import re
import sys

from gh_class_sak import core


class TtyStringIO(io.StringIO):
    """stderr that looks like a terminal, so progress() draws a real bar."""

    def isatty(self):
        return True


def bar_stderr(monkeypatch):
    stream = TtyStringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    return stream


def plain(text):
    """the text with ANSI color codes stripped, for stable assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestProgressMessages:
    def test_noninteractive_messages_print_immediately(self, capsys):
        for item in core.progress([1, 2], "work"):
            core.warn(f"w{item}")
            assert f"w{item}" in capsys.readouterr().err

    def test_messages_are_held_and_replayed_when_the_bar_finishes(
            self, monkeypatch):
        stream = bar_stderr(monkeypatch)
        for item in core.progress([1, 2, 3], "work"):
            core.warn(f"w{item}")
            # flashed on the bar line, not yet committed as a line of its own
            assert f"w{item}" in stream.getvalue()
            assert f"w{item}\n" not in plain(stream.getvalue())
        assert plain(stream.getvalue()).endswith("w1\nw2\nw3\n")

    def test_the_message_stays_up_until_the_next_one_replaces_it(
            self, monkeypatch):
        stream = bar_stderr(monkeypatch)
        for item in core.progress([1, 2, 3], "work"):
            if item == 1:
                core.warn("first")
            if item == 3:
                core.warn("second")
        # updates between the messages keep the first one on the line
        mid_renders = [seg for seg in stream.getvalue().split("\r")
                       if "2/3" in seg]
        assert any("first" in seg for seg in mid_renders)
        # the finished bar's line carries the latest message, not the old one
        final_render = stream.getvalue().split("\r")[-1].split("\n")[0]
        assert "3/3" in final_render
        assert "second" in final_render
        assert "first" not in final_render

    def test_stdout_messages_wait_too_and_keep_their_stream(
            self, monkeypatch, capsys):
        bar_stderr(monkeypatch)
        for item in core.progress([1, 2], "work"):
            core.output(f"o{item}")
            assert capsys.readouterr().out == ""
        assert capsys.readouterr().out == "o1\no2\n"

    def test_a_nested_bars_messages_wait_for_the_outer_bar(self, monkeypatch):
        stream = bar_stderr(monkeypatch)
        def own_lines():
            # replayed messages stand on a line of their own; a flash only
            # ever appears embedded in a bar's line
            return [line for line in plain(stream.getvalue()).split("\n")
                    if line == "held"]

        for _outer in core.progress([1], "outer"):
            for _inner in core.progress([1], "inner"):
                core.warn("held")
            # the inner bar is done, but the outer still owns the terminal:
            # its replay hands the message to the outer hold instead
            assert own_lines() == []
        assert own_lines() == ["held"]

    def test_a_long_message_is_clipped_to_the_bar_line(self, monkeypatch):
        stream = bar_stderr(monkeypatch)
        long = "x" * 500
        for _item in core.progress([1], "work"):
            core.warn(long)
        # the flash was clipped so the bar's \r redraw stays on one line...
        renders = [seg.split("\n")[0] for seg in stream.getvalue().split("\r")]
        assert all(len(plain(seg)) < 200 for seg in renders)
        # ...but the replay carries the full message
        assert long in plain(stream.getvalue())
