"""Load the versioned AgentRegress benchmark manifest into Task objects."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from agents.base_agent import Task


def load_manifest(path: str | Path) -> dict:
    manifest_path = Path(path).resolve()
    with manifest_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError(f"{manifest_path}: manifest must contain a tasks list")
    data["_path"] = manifest_path
    return data


def list_task_ids(manifest: dict) -> list[str]:
    return [entry["id"] for entry in manifest["tasks"]]


def load_task(manifest: dict, task_id: str, repo_path: Optional[str | Path] = None) -> Task:
    entry = next((item for item in manifest["tasks"] if item.get("id") == task_id), None)
    if entry is None:
        raise KeyError(f"Unknown task {task_id!r}; available: {', '.join(list_task_ids(manifest))}")
    manifest_dir = Path(manifest["_path"]).parent
    source_repo = manifest_dir / entry["source_repo"]
    resolved_repo = Path(repo_path).resolve() if repo_path else source_repo.resolve()
    task = Task(
        task_id=entry["id"],
        task_type=entry["type"],
        description=entry["description"],
        repo_path=str(resolved_repo),
        functional_tests=list(entry["functional_tests"]),
        security_tests=list(entry["security_tests"]),
        initial_vulns=list(entry.get("initial_vulns", [])),
        source_files=list(entry["source_files"]),
        editable_paths=list(entry.get("editable_paths", entry["source_files"])),
        build_commands=list(entry.get("build_commands", [])),
    )
    if not source_repo.is_dir():
        raise FileNotFoundError(f"{task_id}: missing benchmark repo {source_repo}")
    return task
