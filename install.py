#!/usr/bin/env python3
"""Install the bundled Agent Skill without changing browser data."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def install(destination):
    source = Path(__file__).resolve().parent / "skills" / "arc-to-zen"
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new --dest or back up/remove the old skill yourself: " + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".build", ".DS_Store"))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--agent", choices=("codex", "claude", "agents"), default="codex")
    target.add_argument("--dest", help="Exact destination skill directory for another compatible agent")
    args = parser.parse_args()
    roots = {"codex": Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
             "claude": Path.home() / ".claude/skills", "agents": Path.home() / ".agents/skills"}
    try:
        destination = install(args.dest or roots[args.agent] / "arc-to-zen")
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    print("Installed: " + str(destination))
    print("Open a new agent chat and invoke $arc-to-zen (or /arc-to-zen if your agent uses slash commands).")


if __name__ == "__main__":
    main()
