"""Prevent accidental backend imports from the separately installed frontend."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "directory,forbidden",
    [
        (
            "frontend",
            {"componentmatch", "sqlalchemy", "langgraph", "langchain", "langchain_deepseek"},
        ),
        (
            "packages/contracts",
            {"componentmatch", "componentmatch_frontend", "sqlalchemy", "streamlit"},
        ),
    ],
)
def test_package_dependency_direction(directory, forbidden):
    for path in Path(directory).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            assert not {name.split(".")[0] for name in modules} & forbidden, str(path)
