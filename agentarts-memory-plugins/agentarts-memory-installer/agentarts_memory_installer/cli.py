"""CLI entry point for agentarts-memory install/uninstall.

Usage:
    agentarts-memory install   [hermes|claude|codex|opencode|openclaw] [--global] [--yes]
    agentarts-memory uninstall [hermes|claude|codex|opencode|openclaw] [--global] [--yes]
    agentarts-memory server    start|stop|status [--yes]
"""

from __future__ import annotations

import argparse
import os
import sys

from .platforms import detect_all, get_platform
from .server_manager import start, status, stop
from .utils import (
    EscapeInterrupt,
    add,
    confirm,
    ensure_credentials,
    expand,
    find,
    list_all,
    remove,
    select_one,
    set_yes,
)

VALID_TARGETS = ("hermes", "claude", "codex", "opencode", "openclaw")

# Platforms that depend on the local adapter server.
SERVER_DEPENDENT = {"claude", "codex", "opencode"}


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with install/uninstall subcommands."""
    parser = argparse.ArgumentParser(
        prog="agentarts-memory",
        description="Install/uninstall AgentArts Memory plugins for supported AI agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in ("install", "uninstall"):
        sp = sub.add_parser(
            cmd,
            help=f"{cmd} a platform plugin",
            description=f"{cmd.capitalize()} AgentArts Memory for the given platform.",
        )
        sp.add_argument(
            "target",
            nargs="?",
            default=None,
            help=f"Target platform ({', '.join(VALID_TARGETS)}). "
            "If omitted, detects interactively.",
        )
        sp.add_argument(
            "--global",
            dest="global_scope",
            action="store_true",
            help="Install to user-level config instead of project-level.",
        )
        sp.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Auto-confirm all prompts (CI-friendly).",
        )

    # Server subcommand
    sp = sub.add_parser(
        "server",
        help="manage the local adapter server",
        description="Start, stop, or check status of the agentarts-memory-server.",
    )
    sp.add_argument(
        "action",
        choices=("start", "stop", "status"),
        help="Server action to perform.",
    )
    sp.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-confirm all prompts (CI-friendly).",
    )

    return parser


def _select_scope(platform_name: str, yes: bool) -> str:
    """Determine install scope (project or global)."""
    platform = get_platform(platform_name)
    if platform and platform.fixed_user_level:
        return "global"
    if yes:
        return "project"
    idx = select_one(
        "Install scope",
        [
            "Project — this project only",
            "Global — all projects",
        ],
        0,
    )
    return "project" if idx == 0 else "global"


def _check_server_dependency(yes: bool) -> None:
    """Print server dependency hint for claude/codex/opencode."""
    print("\nNote: This platform requires the local adapter server (127.0.0.1:8719).")
    print("  Start it with: agentarts-memory-server")
    print("  Or use:   agentarts-memory server start")
    print("  Install:  pip install -e agentarts-memory-plugins/agentarts-memory-code_agent")


def cmd_install(args: argparse.Namespace) -> int:
    """Handle the install subcommand."""
    set_yes(args.yes)

    target = args.target

    # Validate explicit target.
    if target is not None and target not in VALID_TARGETS:
        print(
            f"Error: invalid target '{target}'. " f"Choose from: {', '.join(VALID_TARGETS)}",
            file=sys.stderr,
        )
        return 2

    # openclaw placeholder.
    if target == "openclaw":
        print("openclaw 暂未实现，敬请期待")
        return 0

    # If no target, detect and select.
    if target is None:
        detected = detect_all(args.global_scope)
        if not detected:
            print("\nNo supported platforms detected.")
            print(
                "Install Claude Code, Codex, OpenCode, or Hermes Agent, "
                "then run 'agentarts-memory install' again."
            )
            return 1
        print("Detecting platforms...")
        for name, p in detected:
            print(f"  \u2713 {p.display}")
        options = [p.display for _, p in detected]
        idx = select_one("\nSelect platform", options, 0)
        target = detected[idx][0]

    platform = get_platform(target)
    if platform is None:
        print(f"Error: unknown platform '{target}'", file=sys.stderr)
        return 2

    # Credentials.
    print("\nChecking credentials...")
    creds = ensure_credentials(args.yes)

    # Determine scope.
    scope = "global" if args.global_scope else _select_scope(target, args.yes)

    # Install.
    print(f"\nInstalling {platform.display} ({scope})...")
    result = platform.install(scope, creds, args.yes)

    # Record in manifest.
    add(
        {
            "platform": target,
            "scope": scope,
            "config_dir": result.config_dir,
            "scripts_dir": result.scripts_dir,
            "files": result.files,
            "config_files": result.config_files,
        }
    )

    # Summary.
    print(f"\n\U0001f389 Install complete: {platform.display} ({scope})")
    print(f"  Config dir: {result.config_dir}")
    if result.scripts_dir:
        print(f"  Scripts:    {result.scripts_dir}")
    print(f"  Files:      {len(result.files)} deployed")
    if result.config_files:
        print(f"  Config:     {', '.join(result.config_files)}")

    if target in SERVER_DEPENDENT:
        _check_server_dependency(args.yes)

    print("\nRestart the platform to activate.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Handle the uninstall subcommand."""
    set_yes(args.yes)

    target = args.target

    # Validate explicit target.
    if target is not None and target not in VALID_TARGETS:
        print(
            f"Error: invalid target '{target}'. " f"Choose from: {', '.join(VALID_TARGETS)}",
            file=sys.stderr,
        )
        return 2

    # openclaw placeholder.
    if target == "openclaw":
        print("openclaw 暂未实现，敬请期待")
        return 0

    scope = "global" if args.global_scope else None

    # Find installation to remove.
    entry = None
    if target is not None:
        entry = find(target, scope, None)
        if entry is None:
            print(f"\nNo {target} installation found in manifest.")
            print("Attempting degraded scan...")
            _degraded_scan(target)
            return 1
    else:
        all_installs = list_all()
        if not all_installs:
            print("\nNo installations found.")
            return 1
        print("\nInstalled platforms:")
        options = [
            f"{i['platform']} ({i.get('scope', '?')}) — {i.get('config_dir', '?')}"
            for i in all_installs
        ]
        idx = select_one("Select installation to remove", options, 0)
        entry = all_installs[idx]
        target = entry["platform"]

    platform = get_platform(target)
    if platform is None:
        print(f"Error: unknown platform '{target}'", file=sys.stderr)
        return 2

    # Confirm.
    if not args.yes and not confirm(
        f"Remove {platform.display} from {entry.get('config_dir', '?')}?",
        default=True,
    ):
        print("Cancelled.")
        return 0

    # Uninstall.
    print(f"\nUninstalling {platform.display}...")
    platform.uninstall(entry)

    # Remove from manifest.
    remove(
        target,
        entry.get("scope", ""),
        entry.get("config_dir", ""),
    )

    print(f"\n\u2705 Uninstall complete: {platform.display}")
    print("Restart the platform to apply changes.")
    return 0


def cmd_server(args: argparse.Namespace) -> int:
    """Handle the server subcommand."""
    set_yes(args.yes)

    if args.action == "start":
        return start()
    elif args.action == "stop":
        return stop()
    elif args.action == "status":
        return status()
    return 1


def _degraded_scan(target: str) -> None:
    """Attempt to find and clean up files when manifest is missing."""
    # Scan known platform directories for agentarts-memory markers.

    candidates = {
        "hermes": [expand("~/.hermes/hermes-agent/plugins/memory/agentarts")],
        "claude": [
            expand("~/.claude/agentarts-memory"),
            os.path.join(os.getcwd(), ".claude", "agentarts-memory"),
        ],
        "codex": [
            expand("~/.codex/agentarts-memory"),
            os.path.join(os.getcwd(), ".codex", "agentarts-memory"),
        ],
        "opencode": [expand("~/.config/opencode/plugins/agentarts-memory-capture.ts")],
    }

    found = candidates.get(target, [])
    any_found = False
    for path in found:
        if os.path.exists(path):
            any_found = True
            print(f"  Found leftover: {path}")
            print(f"  Remove manually: rm -rf {path}")

    if not any_found:
        print(f"  No leftover {target} files found.")


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:]).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "install":
            return cmd_install(args)
        elif args.command == "uninstall":
            return cmd_uninstall(args)
        elif args.command == "server":
            return cmd_server(args)
    except EscapeInterrupt:
        print("\nCancelled.")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
