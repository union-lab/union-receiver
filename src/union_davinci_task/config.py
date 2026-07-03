from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE_ROOT = PROJECT_ROOT.parent


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if raw:
        return Path(raw).expanduser().resolve()
    return default.resolve()


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class TaskSettings:
    agent_path: Path
    knowledgebase_path: Path
    interval_seconds: int
    batch_size: int
    agent_env_file: str
    database_name: str


def load_settings() -> TaskSettings:
    return TaskSettings(
        agent_path=_path_from_env(
            "UNION_AGENT_PATH",
            DEFAULT_WORKSPACE_ROOT / "union-lab-union-agent-git-https",
        ),
        knowledgebase_path=_path_from_env(
            "UNION_KNOWLEDGEBASE_PATH",
            DEFAULT_WORKSPACE_ROOT / "union-lab-union-knowledgebase-git-https",
        ),
        interval_seconds=max(10, _int_from_env("DAVINCI_TASK_INTERVAL_SECONDS", 300)),
        batch_size=max(1, _int_from_env("DAVINCI_TASK_BATCH_SIZE", 1)),
        agent_env_file=os.environ.get("UNION_AGENT_ENV_FILE", ".env.union-dev"),
        database_name=os.environ.get("DAVINCI_TASK_DATABASE_NAME", "union_prod"),
    )
