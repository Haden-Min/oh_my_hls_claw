from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .utils.console import Console, Panel, ProgressConsole


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oh-my-hls-claw",
        description="Oh_My_HLS_Claw - AI-powered Digital System Design Agent",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize language, API access, and simulator settings")

    new_parser = subparsers.add_parser("new", help="Start a new design project")
    new_parser.add_argument("--desc", type=str, help="Design description in natural language")
    new_parser.add_argument("--ref", type=str, help="Path to reference software code")
    new_parser.add_argument("--board", type=str, help="Target FPGA board")
    new_parser.add_argument("--project", type=str, help="Override project name")
    new_parser.add_argument("--approve-all", action="store_true", help="Auto-approve checkpoints for this run")

    resume_parser = subparsers.add_parser("resume", help="Resume an existing project")
    resume_parser.add_argument("--project", required=True)

    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("--project", required=True)

    cost_parser = subparsers.add_parser("cost", help="Show project cost breakdown")
    cost_parser.add_argument("--project", required=True)

    clean_parser = subparsers.add_parser("clean", help="Remove generated project outputs")
    clean_scope = clean_parser.add_mutually_exclusive_group(required=True)
    clean_scope.add_argument("--project", type=str, help="Remove outputs for one project")
    clean_scope.add_argument("--all", action="store_true", help="Remove all generated project outputs")
    return parser


async def start_new_project(args: argparse.Namespace) -> None:
    from .orchestrator import Orchestrator

    root = Path(__file__).resolve().parent.parent
    progress_console = ProgressConsole(Console())
    orchestrator = Orchestrator(root)
    orchestrator.context.checkpoint_manager.auto_approve = bool(args.approve_all)
    if args.ref:
        ref_text = Path(args.ref).read_text(encoding="utf-8")
        user_input = f"Reference software:\n{ref_text}"
    elif args.desc:
        user_input = args.desc
    else:
        user_input = progress_console.input("Describe the digital system to design: ").strip()
    result = await orchestrator.run_project(user_input, project_name=args.project, board=args.board)
    orchestrator.save_costs(result["project_name"])
    status = result.get("status", "unknown")
    if status == "completed":
        progress_console.print(Panel(f"Project completed: {result['project_name']}", title="Done"))
        return

    audit = result.get("final_audit", {})
    reason = audit.get("reason") or result.get("error") or "Project did not reach a completed state."
    problem_step = audit.get("step")
    problem_module = audit.get("module")
    detail = f"Project status: {status}"
    if problem_step is not None and problem_module:
        detail += f"\nBlocked at step {problem_step} ({problem_module})"
    detail += f"\nReason: {reason}"
    progress_console.print(Panel(detail, title="Not Done"))


async def resume_project(args: argparse.Namespace) -> None:
    from .orchestrator import Orchestrator

    root = Path(__file__).resolve().parent.parent
    orchestrator = Orchestrator(root)
    state = orchestrator.resume_project(args.project)
    Console().print(Panel(str(state), title=f"Resume: {args.project}"))


def show_status(args: argparse.Namespace) -> None:
    from .orchestrator import Orchestrator

    root = Path(__file__).resolve().parent.parent
    orchestrator = Orchestrator(root)
    state = orchestrator.status(args.project)
    Console().print(Panel(str(state), title=f"Status: {args.project}"))


def show_cost(args: argparse.Namespace) -> None:
    from .orchestrator import Orchestrator

    root = Path(__file__).resolve().parent.parent
    orchestrator = Orchestrator(root)
    cost = orchestrator.cost(args.project)
    Console().print(Panel(str(cost), title=f"Cost: {args.project}"))


def clean_outputs(args: argparse.Namespace) -> None:
    from .orchestrator import Orchestrator

    root = Path(__file__).resolve().parent.parent
    console = ProgressConsole(Console())
    orchestrator = Orchestrator(root)
    removed = orchestrator.clean(project_name=args.project, all_projects=args.all)
    if removed:
        console.print(Panel("\n".join(removed), title="Removed"))
    else:
        target = args.project or "all generated project outputs"
        console.print(Panel(f"Nothing to remove for {target}.", title="Clean"))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent

    if args.command == "init":
        from .orchestrator import initialize_system

        asyncio.run(initialize_system(root))
    elif args.command == "new":
        asyncio.run(start_new_project(args))
    elif args.command == "resume":
        asyncio.run(resume_project(args))
    elif args.command == "status":
        show_status(args)
    elif args.command == "cost":
        show_cost(args)
    elif args.command == "clean":
        clean_outputs(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
