"""CLI tests: home view, TOON output, exit codes, arg validation."""

import pytest

from etmoney_lyr.cli_main import (
    _toon_kv,
    _toon_quote,
    build_parser,
    main,
)


class TestToon:
    @pytest.mark.parametrize(
        ("val", "want"),
        [
            ("plain", "plain"),
            ('has"quote', '"has\\"quote"'),
            ("has:colon", '"has:colon"'),
            ("-starts-dash", '"-starts-dash"'),
            ("123", '"123"'),
            ("true", '"true"'),
            ("", '""'),
            ("a,b", '"a,b"'),
        ],
    )
    def test_quote(self, val, want):
        assert _toon_quote(val) == want

    def test_kv_types(self):
        assert _toon_kv("n", 5) == "n: 5"
        assert _toon_kv("f", 1.5) == "f: 1.5"
        assert _toon_kv("b", True) == "b: true"
        assert _toon_kv("x", None) == "x: null"
        assert _toon_kv("s", "hi there") == "s: hi there"


class TestParser:
    def test_unknown_screen_rejected(self, capsys):
        with pytest.raises(SystemExit) as e:
            build_parser().parse_args(["stocks", "not_a_screen"])
        assert e.value.code == 2

    def test_known_screen_accepted(self):
        args = build_parser().parse_args(["stocks", "top_gainers"])
        assert args.screen == "top_gainers"

    def test_funds_defaults(self):
        args = build_parser().parse_args(["funds"])
        assert args.duration == "1y" and args.size == 20 and args.order == "desc"


class TestMain:
    @pytest.fixture(autouse=True)
    def _tty(self, monkeypatch):
        # pytest captures stdin (not a tty); force "human at terminal" for
        # home-view tests so main([]) doesn't try to serve MCP.
        import sys as _sys

        monkeypatch.setattr(_sys.stdin, "isatty", lambda: True)

    def test_home_view_no_network(self, capsys):
        # must not touch network; if it did, this would fail in offline CI
        main([])
        out = capsys.readouterr().out
        assert "etmoney-lyr" in out and "quick start" in out

    def test_piped_stdin_starts_mcp_server(self, monkeypatch):
        # AXI/family convention: piped stdin = MCP client -> serve, not home view
        import sys as _sys

        monkeypatch.setattr(_sys.stdin, "isatty", lambda: False)
        called = {}
        monkeypatch.setattr("etmoney_lyr.cli_main._run_mcp_server", lambda: called.update(x=1))
        main([])
        assert called == {"x": 1}

    def test_piped_stdin_with_command_still_runs_command(self, capsys):
        # subcommands never become the server regardless of TTY state
        with pytest.raises(SystemExit) as e:
            main(["bogus-cmd"])
        assert e.value.code == 2

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as e:
            main(["--version"])
        assert e.value.code == 0
        assert "0.1.0" in capsys.readouterr().out

    def test_list_tools(self, capsys):
        main(["--list-tools"])
        out = capsys.readouterr().out
        assert "mf_search" in out and "stock_detail" in out

    def test_list_tools_fields_filter(self, capsys):
        main(["--list-tools", "--fields", "stock"])
        out = capsys.readouterr().out
        assert "mf_search" not in out
        assert "stock_screen" in out

    def test_unknown_command_exits_2(self, capsys):
        with pytest.raises(SystemExit) as e:
            main(["bogus-cmd"])
        assert e.value.code == 2

    def test_compare_bad_count_exits_2(self, capsys):
        with pytest.raises(SystemExit) as e:
            main(["compare", "19230"])  # needs >= 2 ids
        assert e.value.code == 2
        assert "2..4" in capsys.readouterr().out


class TestHomeViewContentFirst:
    """AXI §8/§9: bare invocation teaches next steps without any I/O."""

    def test_mentions_all_key_commands(self, monkeypatch, capsys):
        import sys as _sys

        monkeypatch.setattr(_sys.stdin, "isatty", lambda: True)
        main([])
        out = capsys.readouterr().out
        for token in ["search", "fund ", "stocks", "--list-tools", "mcpServers"]:
            assert token in out
