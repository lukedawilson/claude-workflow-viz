"""Command line entry point dispatching to the `serve`, `hook` and `install` subcommands."""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from claude_workflow_viz.dashboard.server import serve
from claude_workflow_viz.graph.graph import Graph, GraphError
from claude_workflow_viz.install.installer import DEFAULT_VIZ_DIR, Installer, InstallError
from claude_workflow_viz.workflow.hook_command import run_hook


def _serve(arguments: argparse.Namespace) -> int:
    graph = None
    if arguments.graph is not None:
        graph = Graph.load(arguments.graph)
        if isinstance(graph, GraphError):
            print(f"claude-workflow-viz: {graph.message}", file=sys.stderr)
            return 1
    serve(arguments.port, graph)
    return 0


def _hook(_arguments: argparse.Namespace) -> int:
    return run_hook()


def _install(arguments: argparse.Namespace) -> int:
    try:
        summary = Installer().run(Path.cwd(), Path(arguments.viz_dir), arguments.force)
    except (InstallError, OSError) as error:
        print(f"claude-workflow-viz: {error}", file=sys.stderr)
        return 1
    print(summary.render())
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-workflow-viz",
        description="Live Mermaid flowchart of a Claude Code Workflow run.",
    )
    subcommands = parser.add_subparsers(
        dest="command", required=True, metavar="{serve,hook,install}"
    )
    serve_parser = subcommands.add_parser("serve", help="run the local server and web UI")
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8322,
        help="port to listen on (default 8322; a busy port falls back to an OS-picked one)",
    )
    serve_parser.add_argument(
        "--graph",
        default=None,
        help="path to a graph YAML config; without it a linear graph is built from seen stages",
    )
    serve_parser.set_defaults(handler=_serve)
    hook = subcommands.add_parser("hook", help="handle a Claude Code hook event from stdin")
    hook.set_defaults(handler=_hook)
    install = subcommands.add_parser(
        "install", help="wire this repo: verify, register hooks, create the /viz command"
    )
    install.add_argument(
        "--viz-dir",
        default=str(DEFAULT_VIZ_DIR),
        help="directory for agent-generated viz.yaml files (default .claude-local/viz)",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing .claude/commands/viz.md",
    )
    install.set_defaults(handler=_install)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments_list = sys.argv[1:] if argv is None else list(argv)
    if arguments_list[:1] == ["hook"]:
        # Bypass argparse so nothing, not even a usage error, reaches stderr on the hook path.
        return run_hook()
    arguments = _build_parser().parse_args(arguments_list)
    handler: Callable[[argparse.Namespace], int] = arguments.handler
    return handler(arguments)
