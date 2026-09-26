from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def test_workspace(request: pytest.FixtureRequest) -> Path:
    """Keep generated test inputs in the project-owned output directory."""
    safe_name = request.node.name.replace("[", "_").replace("]", "_")
    workspace = Path(__file__).resolve().parents[1] / "output" / "test_workspace" / safe_name
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace
