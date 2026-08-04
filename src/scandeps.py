import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Set


IMPORT_RE = re.compile(
    r"^\s*import\s+([A-Za-z_][\w\.]*\s*(?:,\s*[A-Za-z_][\w\.]*)*)",
    re.MULTILINE,
)
FROM_RE = re.compile(r"^\s*from\s+([A-Za-z_][\w\.]*)\s+import", re.MULTILINE)
STD_LIB = (
    set(getattr(sys, "stdlib_module_names", []))
    | set(sys.builtin_module_names)
    | {"__future__", "__main__"}
)


def _base_package(module: str) -> str:
    return module.split(".", 1)[0].strip()


def scan_code(code: str) -> Set[str]:
    # Depends on Python 3.10+ for sys.stdlib_module_names
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10+ required for stdlib_module_names")
    pkgs: Set[str] = set()
    for match in IMPORT_RE.finditer(code):
        for mod in match.group(1).split(","):
            pkgs.add(_base_package(mod))
    for match in FROM_RE.finditer(code):
        pkgs.add(_base_package(match.group(1)))
    return {pkg for pkg in pkgs if pkg and pkg not in STD_LIB}


def read_notebook(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        notebook = json.load(handle)
    cells = notebook.get("cells") or []
    lines: list[str] = []
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        if isinstance(source, str):
            lines.append(source)
        else:
            lines.extend(str(line) for line in source)
    return "\n".join(lines)


def read_qmd(path: str) -> str:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    code: list[str] = []
    in_block = False
    for line in lines:
        if in_block:
            if line.startswith("```"):
                in_block = False
                code.append("")
            else:
                code.append(line.rstrip("\r"))
        elif line.startswith("```{python"):
            in_block = True
    return "\n".join(code)


def _local_package_exists(dirpath: str, name: str) -> bool:
    return os.path.isdir(os.path.join(dirpath, name)) or os.path.isfile(
        os.path.join(dirpath, f"{name}.py")
    )


def scan_project(root: str) -> list[str]:
    imports: Set[str] = set()
    for dirpath, _, files in os.walk(root):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            path = os.path.join(dirpath, filename)
            code = ""
            if ext == ".py":
                code = Path(path).read_text(encoding="utf-8")
            elif ext == ".ipynb":
                code = read_notebook(path)
            elif ext == ".qmd":
                code = read_qmd(path)
            if not code:
                continue
            names = {name for name in scan_code(code) if not _local_package_exists(dirpath, name)}
            imports.update(names)
    return sorted(imports)
