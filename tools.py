from __future__ import annotations

import ast
import base64
import inspect
import json
import logging
import pathlib
import subprocess
import sys
import traceback
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import get_settings

LOGGER = logging.getLogger(__name__)
SETTINGS = get_settings()


SECURITY_WARNING = (
    "python_execute is high risk. In production, avoid running untrusted code in-process and use an isolated "
    "sandbox provider (e.g., E2B, Firecracker microVMs, or hardened Docker sandbox)."
)


def _http_get_json(url: str) -> dict[str, Any]:
    request = Request(url=url, method="GET")
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload)


def web_search(query: str, max_results: int = 5, serpapi_api_key: str | None = None) -> dict[str, Any]:
    """Search the public web via SerpAPI.

    Use this tool when the task needs fresh, external information (news, prices,
    weather, current events, or anything not guaranteed to be in model memory).
    Input expects a natural-language `query` and optional `max_results`.
    """
    api_key = serpapi_api_key or SETTINGS.serpapi_api_key
    if not api_key:
        return {
            "ok": False,
            "error": "Missing SERPAPI_API_KEY. Set it in your environment.",
            "results": [],
        }

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": max_results,
    }
    url = f"https://serpapi.com/search.json?{urlencode(params)}"

    try:
        data = _http_get_json(url)
        organic_results = data.get("organic_results", [])[:max_results]
        reduced = [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in organic_results
        ]
        return {"ok": True, "query": query, "results": reduced}
    except (HTTPError, URLError, TimeoutError) as exc:
        return {"ok": False, "error": f"web_search failed: {exc}", "results": []}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Invalid JSON from SerpAPI: {exc}", "results": []}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_ast(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left**right
    raise ValueError("Expression contains unsupported syntax.")


def calculator(expression: str) -> dict[str, Any]:
    """Evaluate a pure arithmetic expression safely.

    Use this for deterministic math like +, -, *, /, %, and exponentiation.
    Pass only the expression string (example: "(23 - 43) * 2").
    """
    try:
        parsed = ast.parse(expression, mode="eval")
        value = _eval_ast(parsed)
        rounded = int(value) if value.is_integer() else value
        return {"ok": True, "expression": expression, "result": rounded}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"calculator failed: {exc}"}


_PYTHON_SANDBOX_RUNNER = r"""
import ast
import base64
import builtins
import contextlib
import io
import json
import traceback
import sys

ALLOWED_MODULES = {
    "math",
    "statistics",
    "random",
    "datetime",
    "itertools",
    "collections",
    "functools",
    "re",
    "json",
}

BLOCKED_CALLS = {"open", "exec", "eval", "compile", "input", "globals", "locals"}


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root_name = name.split(".", 1)[0]
    if root_name not in ALLOWED_MODULES:
        raise ImportError(f"Import of module '{root_name}' is blocked in sandbox.")
    return builtins.__import__(name, globals, locals, fromlist, level)


safe_builtins = {
    "print": print,
    "len": len,
    "range": range,
    "sum": sum,
    "min": min,
    "max": max,
    "sorted": sorted,
    "enumerate": enumerate,
    "abs": abs,
    "round": round,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "zip": zip,
    "map": map,
    "filter": filter,
    "all": all,
    "any": any,
    "__import__": safe_import,
}


def execute() -> None:
    encoded = sys.argv[1]
    code = base64.b64decode(encoded.encode("ascii")).decode("utf-8", errors="replace")
    stdout = io.StringIO()
    locals_scope = {}

    try:
        tree = ast.parse(code, mode="exec")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".", 1)[0]
                    if module not in ALLOWED_MODULES:
                        raise ValueError(f"Import '{module}' is not allowed in sandbox.")
            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".", 1)[0]
                if module not in ALLOWED_MODULES:
                    raise ValueError(f"Import '{module}' is not allowed in sandbox.")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                raise ValueError(f"Call to '{node.func.id}' is blocked in sandbox.")

        globals_scope = {"__builtins__": safe_builtins}
        with contextlib.redirect_stdout(stdout):
            exec(compile(tree, "<python_execute_sandbox>", "exec"), globals_scope, locals_scope)

        safe_locals = {
            key: repr(value)
            for key, value in locals_scope.items()
            if not key.startswith("__")
        }
        payload = {
            "ok": True,
            "stdout": stdout.getvalue(),
            "locals": safe_locals,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "error": f"python_execute failed: {exc}",
            "traceback": traceback.format_exc(),
            "stdout": stdout.getvalue(),
        }

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    execute()
"""


def _trim_large_output(payload: dict[str, Any]) -> dict[str, Any]:
    max_chars = max(512, int(SETTINGS.python_exec_max_output_chars))

    for key in ("stdout", "traceback", "error"):
        value = payload.get(key)
        if isinstance(value, str) and len(value) > max_chars:
            payload[key] = value[:max_chars] + "\n...[truncated]"

    return payload


def _parse_sandbox_output(completed: subprocess.CompletedProcess[str], mode: str) -> dict[str, Any]:
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if not stdout:
        return {
            "ok": False,
            "error": f"python_execute sandbox produced no output (mode={mode}, returncode={completed.returncode}).",
            "stderr": stderr,
            "sandbox": {"mode": mode},
        }

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "python_execute sandbox returned invalid JSON.",
            "stdout": stdout,
            "stderr": stderr,
            "sandbox": {"mode": mode},
        }

    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "error": "python_execute sandbox returned non-dict payload.",
            "stdout": stdout,
            "sandbox": {"mode": mode},
        }

    parsed["sandbox"] = {
        "mode": mode,
        "hardening_note": (
            "For stronger isolation, set PYTHON_EXEC_SANDBOX_MODE=docker and run with a locked-down Docker daemon."
        ),
    }
    return _trim_large_output(parsed)


def _run_python_subprocess_sandbox(code: str) -> dict[str, Any]:
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    command = [sys.executable, "-I", "-c", _PYTHON_SANDBOX_RUNNER, encoded]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(SETTINGS.python_exec_timeout_seconds)),
        )
        return _parse_sandbox_output(completed, mode="subprocess")
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "python_execute sandbox timed out.",
            "sandbox": {"mode": "subprocess"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"python_execute sandbox failed: {exc}",
            "traceback": traceback.format_exc(),
            "sandbox": {"mode": "subprocess"},
        }


def _run_python_docker_sandbox(code: str) -> dict[str, Any]:
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--memory",
        SETTINGS.python_exec_docker_memory,
        SETTINGS.python_exec_docker_image,
        "python",
        "-I",
        "-c",
        _PYTHON_SANDBOX_RUNNER,
        encoded,
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(SETTINGS.python_exec_timeout_seconds)),
        )
        return _parse_sandbox_output(completed, mode="docker")
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "Docker executable not found. Install Docker or switch PYTHON_EXEC_SANDBOX_MODE to subprocess.",
            "sandbox": {"mode": "docker"},
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "python_execute docker sandbox timed out.",
            "sandbox": {"mode": "docker"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"python_execute docker sandbox failed: {exc}",
            "traceback": traceback.format_exc(),
            "sandbox": {"mode": "docker"},
        }


def python_execute(code: str) -> dict[str, Any]:
    """Run short Python snippets in a restricted sandbox.

    Use this tool for data transformation or small computations that are easier in
    Python than plain text reasoning. Execution is isolated in subprocess mode by
    default and can use Docker isolation when configured.

    Security note: this is still not fully safe for hostile multi-tenant workloads.
    Prefer a dedicated external sandbox runtime in production.
    """
    mode = (SETTINGS.python_exec_sandbox_mode or "subprocess").strip().lower()
    if mode in {"e2b", "external"}:
        return {
            "ok": False,
            "error": "External sandbox mode is configured but not integrated yet.",
            "security_warning": SECURITY_WARNING,
            "next_step": (
                "Integrate an external sandbox provider and replace python_execute with remote execution calls."
            ),
            "sandbox": {"mode": mode},
        }

    LOGGER.warning("%s", SECURITY_WARNING)
    if mode == "docker":
        docker_result = _run_python_docker_sandbox(code)
        if docker_result.get("ok"):
            if isinstance(docker_result, dict):
                docker_result.setdefault("security_warning", SECURITY_WARNING)
            return docker_result
        LOGGER.warning("Docker sandbox unavailable or failed; falling back to subprocess sandbox: %s", docker_result.get("error"))

    result = _run_python_subprocess_sandbox(code)
    if isinstance(result, dict):
        result.setdefault("security_warning", SECURITY_WARNING)
    return result


def file_reader(path: str, file_root: str = ".", max_chars: int = 12000) -> dict[str, Any]:
    """Read a text file under the allowed project root.

    Use this tool when the task needs local project context from files. Hidden files
    and directories are blocked, and traversal outside `file_root` is rejected.
    """
    try:
        root = pathlib.Path(file_root).resolve()
        requested = pathlib.Path(path)
        target = (root / requested).resolve() if not requested.is_absolute() else requested.resolve()

        try:
            relative_target = target.relative_to(root)
        except ValueError:
            return {"ok": False, "error": "Path escapes file_root."}

        if any(part.startswith(".") for part in relative_target.parts):
            return {
                "ok": False,
                "error": "Access to hidden files or directories is blocked.",
            }

        if not target.exists() or not target.is_file():
            return {"ok": False, "error": f"File not found: {path}"}

        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = content[:max_chars]
        return {
            "ok": True,
            "path": str(relative_target),
            "content": truncated,
            "truncated": len(content) > len(truncated),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"file_reader failed: {exc}"}


TOOL_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "web_search": {"query": "string", "max_results": "integer (optional)"},
    "calculator": {"expression": "string"},
    "python_execute": {"code": "string"},
    "file_reader": {"path": "string", "max_chars": "integer (optional)"},
}


TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "web_search": web_search,
    "calculator": calculator,
    "python_execute": python_execute,
    "file_reader": file_reader,
}


def _tool_description(function: Callable[..., dict[str, Any]]) -> str:
    doc = inspect.getdoc(function)
    if doc:
        return doc
    return "No tool description available."


def get_tool_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name, function in TOOL_FUNCTIONS.items():
        specs.append(
            {
                "name": name,
                "description": _tool_description(function),
                "input_schema": TOOL_INPUT_SCHEMAS.get(name, {}),
            }
        )
    return specs


def run_tool(tool_name: str, tool_input: dict[str, Any] | None = None, file_root: str = ".") -> dict[str, Any]:
    payload = tool_input or {}

    if tool_name not in TOOL_FUNCTIONS:
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    if tool_name == "web_search":
        return web_search(
            query=str(payload.get("query", "")),
            max_results=int(payload.get("max_results", 5)),
        )
    if tool_name == "calculator":
        return calculator(expression=str(payload.get("expression", "")))
    if tool_name == "python_execute":
        return python_execute(code=str(payload.get("code", "")))
    if tool_name == "file_reader":
        return file_reader(
            path=str(payload.get("path", "")),
            file_root=file_root,
            max_chars=int(payload.get("max_chars", 12000)),
        )

    return {"ok": False, "error": f"No dispatcher for tool: {tool_name}"}