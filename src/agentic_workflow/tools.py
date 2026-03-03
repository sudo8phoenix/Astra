from __future__ import annotations

"""Tool implementations used by the Phase 2 executor."""

import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .state import ToolResult


def _ok(output: str, metadata: dict[str, Any] | None = None) -> ToolResult:
    """Build a successful tool response payload."""

    return {
        "status": "success",
        "output": output,
        "metadata": metadata or {},
    }


def _error(message: str, metadata: dict[str, Any] | None = None) -> ToolResult:
    """Build an error tool response payload."""

    return {
        "status": "error",
        "output": message,
        "metadata": metadata or {},
    }


def web_search_tool(query: str) -> ToolResult:
    """Fetch a concise web summary using DuckDuckGo's instant-answer API."""

    try:
        params = urlencode({"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
        url = f"https://api.duckduckgo.com/?{params}"
        with urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))

        heading = str(payload.get("Heading", "")).strip()
        abstract = str(payload.get("AbstractText", "")).strip()
        related_topics = payload.get("RelatedTopics", [])
        related_snippets: list[str] = []
        for topic in related_topics[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                related_snippets.append(str(topic["Text"]))

        parts = [part for part in [heading, abstract] if part]
        if related_snippets:
            parts.append("Related: " + " | ".join(related_snippets))
        output = "\n".join(parts).strip() or "No concise result found."
        return _ok(output, {"tool": "web_search", "query": query})
    except Exception as exc:  # noqa: BLE001
        return _error(f"web_search failed: {exc}", {"tool": "web_search", "query": query})


def python_execute_tool(code: str) -> ToolResult:
    """Run Python code in a short-lived subprocess and capture combined output."""

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
            temp_file.write(code)
            temp_path = temp_file.name

        completed = subprocess.run(  # noqa: S603
            ["python3", temp_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        status = "success" if completed.returncode == 0 else "error"
        return {
            "status": status,
            "output": output.strip() or "(no output)",
            "metadata": {"tool": "python_execute", "returncode": completed.returncode},
        }
    except subprocess.TimeoutExpired:
        return _error("python_execute timed out.", {"tool": "python_execute"})
    except Exception as exc:  # noqa: BLE001
        return _error(f"python_execute failed: {exc}", {"tool": "python_execute"})
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def file_reader_tool(path: str, file_root: str) -> ToolResult:
    """Read a file under the workspace root while preventing path traversal."""

    try:
        root = Path(file_root).resolve()
        target = (root / path).resolve()
        if not str(target).startswith(str(root)):
            return _error("Access denied: path outside workspace.", {"tool": "file_reader", "path": path})
        if not target.exists() or not target.is_file():
            return _error("File not found.", {"tool": "file_reader", "path": path})
        text = target.read_text(encoding="utf-8")
        return _ok(text, {"tool": "file_reader", "path": str(target)})
    except Exception as exc:  # noqa: BLE001
        return _error(f"file_reader failed: {exc}", {"tool": "file_reader", "path": path})


def calculator_tool(expression: str) -> ToolResult:
    """Safely evaluate arithmetic expressions using an AST allow-list."""

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Load,
    )
    try:
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                return _error("Unsupported expression. Only arithmetic operations are allowed.", {"tool": "calculator"})
        value = eval(compile(tree, "<calculator>", "eval"), {"__builtins__": {}}, {})  # noqa: S307
        return _ok(str(value), {"tool": "calculator", "expression": expression})
    except Exception as exc:  # noqa: BLE001
        return _error(f"calculator failed: {exc}", {"tool": "calculator", "expression": expression})