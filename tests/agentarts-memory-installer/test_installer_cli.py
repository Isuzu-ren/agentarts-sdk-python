"""Tests for CLI entry point (P0 + P6)."""

import os

import pytest
from agentarts_memory_installer import cli
from agentarts_memory_installer.utils import ENV_API_KEY, ENV_REGION, ENV_SPACE_ID, expand, find

VALID_TARGETS = cli.VALID_TARGETS
build_parser = cli.build_parser
main = cli.main


def _set_home_and_creds(monkeypatch, tmp_path):
    """Redirect HOME to tmp and set valid credentials."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(ENV_SPACE_ID, "test-space-12345")
    monkeypatch.setenv(ENV_API_KEY, "test-api-key-abcdef-123456")
    monkeypatch.setenv(ENV_REGION, "cn-north-4")


# ── Parser tests ────────────────────────────────────────────────────


class TestParser:
    def test_install_help_exits_clean(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["install", "--help"])
        assert exc.value.code == 0

    def test_uninstall_help_exits_clean(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["uninstall", "--help"])
        assert exc.value.code == 0

    def test_no_subcommand_errors(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_install_parses_target(self):
        args = build_parser().parse_args(["install", "hermes"])
        assert args.command == "install"
        assert args.target == "hermes"
        assert args.global_scope is False
        assert args.yes is False

    def test_install_global_flag(self):
        args = build_parser().parse_args(["install", "claude", "--global"])
        assert args.global_scope is True

    def test_install_yes_flag(self):
        args = build_parser().parse_args(["install", "codex", "--yes"])
        assert args.yes is True
        args2 = build_parser().parse_args(["install", "codex", "-y"])
        assert args2.yes is True

    def test_install_no_target_ok(self):
        args = build_parser().parse_args(["install"])
        assert args.target is None

    def test_valid_targets(self):
        assert VALID_TARGETS == ("hermes", "claude", "codex", "opencode", "openclaw")


# ── openclaw placeholder ────────────────────────────────────────────


class TestOpenClawPlaceholder:
    def test_install_openclaw(self, capsys):
        rc = main(["install", "openclaw"])
        assert rc == 0
        assert "暂未实现" in capsys.readouterr().out

    def test_uninstall_openclaw(self, capsys):
        rc = main(["uninstall", "openclaw"])
        assert rc == 0
        assert "暂未实现" in capsys.readouterr().out


# ── Invalid target ──────────────────────────────────────────────────


class TestInvalidTarget:
    def test_install_invalid(self, capsys):
        rc = main(["install", "bogus"])
        assert rc == 2

    def test_uninstall_invalid(self, capsys):
        rc = main(["uninstall", "bogus"])
        assert rc == 2


# ── No detection / no installs ──────────────────────────────────────


class TestNoTargets:
    def test_install_no_target_no_detection(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        # No ~/.claude, ~/.codex, ~/.hermes, ~/.config/opencode
        rc = main(["install", "--yes"])
        assert rc == 1
        assert "No supported platforms detected" in capsys.readouterr().out

    def test_uninstall_no_target_no_installs(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        rc = main(["uninstall", "--yes"])
        assert rc == 1
        assert "No installations found" in capsys.readouterr().out

    def test_uninstall_target_not_found(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        rc = main(["uninstall", "hermes", "--yes"])
        assert rc == 1
        assert "No hermes installation found" in capsys.readouterr().out


# ── End-to-end: install + uninstall hermes ────────────────────────────


class TestEndToEndHermes:
    def test_install_hermes_yes(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        rc = main(["install", "hermes", "--yes"])
        assert rc == 0

        # Verify files deployed.
        plugin_dir = expand("~/.hermes/hermes-agent/plugins/memory/agentarts")
        assert os.path.isdir(plugin_dir)
        assert os.path.isfile(os.path.join(plugin_dir, "provider.py"))

        # Verify manifest has record.
        found = find("hermes")
        assert found is not None
        assert found["scope"] == "global"  # hermes is fixed_user_level

    def test_install_hermes_global_yes(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        rc = main(["install", "hermes", "--global", "--yes"])
        assert rc == 0

        # hermes is fixed_user_level, so scope should be "global" regardless.
        found = find("hermes")
        assert found is not None
        assert found["scope"] == "global"

    def test_uninstall_hermes_after_install(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)

        # Install first.
        main(["install", "hermes", "--global", "--yes"])

        # Uninstall.
        rc = main(["uninstall", "hermes", "--global", "--yes"])
        assert rc == 0

        # Verify cleaned.
        plugin_dir = expand("~/.hermes/hermes-agent/plugins/memory/agentarts")
        assert not os.path.exists(plugin_dir)
        assert find("hermes") is None


# ── End-to-end: install + uninstall claude ───────────────────────────


class TestEndToEndClaude:
    def test_install_claude_global_yes(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        rc = main(["install", "claude", "--global", "--yes"])
        assert rc == 0

        scripts_dir = os.path.join(expand("~/.claude"), "agentarts-memory", "scripts")
        assert os.path.isdir(scripts_dir)

        settings_path = os.path.join(expand("~/.claude"), "settings.json")
        assert os.path.isfile(settings_path)

        found = find("claude")
        assert found is not None
        assert found["scope"] == "global"

    def test_uninstall_claude_after_install(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)

        main(["install", "claude", "--global", "--yes"])
        rc = main(["uninstall", "claude", "--global", "--yes"])
        assert rc == 0

        scripts_dir = os.path.join(expand("~/.claude"), "agentarts-memory", "scripts")
        assert not os.path.exists(scripts_dir)
        assert find("claude") is None

    def test_server_dependency_hint_printed(self, monkeypatch, tmp_path, capsys):
        _set_home_and_creds(monkeypatch, tmp_path)
        main(["install", "claude", "--global", "--yes"])
        out = capsys.readouterr().out
        assert "127.0.0.1:8719" in out
