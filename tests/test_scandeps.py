import json
from pathlib import Path

import pytest

from scandeps import read_notebook, read_qmd, scan_code, scan_project


FIXTURES = Path(__file__).parent / "fixtures"


def test_scan_code_parses_various_imports():
    assert scan_code(
        """
import pandas.core.frame, requests
    from sklearn.model_selection import train_test_split
\tfrom torch import (
        nn,
        optim,
    )
    import typing  # stdlib should be dropped
    """
    ) == {"pandas", "requests", "sklearn", "torch"}


def test_scan_code_filters_stdlib_and_builtins():
    assert (
        scan_code(
            "import sys, json\nfrom builtins import open\nfrom __future__ import annotations\n"
        )
        == set()
    )


def test_scan_code_requires_python_310(monkeypatch):
    monkeypatch.setattr("scandeps.sys.version_info", (3, 9, 9))
    with pytest.raises(RuntimeError):
        scan_code("import requests")


def test_read_notebook_collects_only_code_cells():
    lines = [
        line
        for line in read_notebook(str(FIXTURES / "sample_notebook.ipynb")).splitlines()
        if line
    ]
    assert lines == [
        "import pandas",
        "import numpy as np",
        "from sklearn.model_selection import train_test_split",
        "print('done')",
    ]


def test_read_qmd_extracts_python_blocks_only():
    assert read_qmd(str(FIXTURES / "sample_report.qmd")).splitlines() == [
        "import pandas as pd",
        "print(pd.__version__)",
        "",
        "from sklearn import metrics",
    ]


def test_scan_project_collects_imports_across_formats(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "localpkg").mkdir()
    (project / "localpkg" / "__init__.py").write_text("")
    (project / "localmod.py").write_text("# local module\n")

    (project / "app.py").write_text(
        """
import requests, typing
from pandas.core.frame import DataFrame
from torch import nn
import localpkg
from localmod import value
"""
    )

    notebook_dir = project / "notebooks"
    notebook_dir.mkdir()
    (notebook_dir / "helpers.py").write_text("# helper\n")
    with (notebook_dir / "analysis.ipynb").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "source": [
                            "import matplotlib.pyplot\n",
                            "from scipy import stats\n",
                            "import helpers\n",
                        ],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            handle,
        )

    docs = project / "docs"
    docs.mkdir()
    (docs / "report.qmd").write_text(
        """\
```{python}
import seaborn
from sklearn.linear_model import LogisticRegression
```
"""
    )

    assert scan_project(str(project)) == [
        "matplotlib",
        "pandas",
        "requests",
        "scipy",
        "seaborn",
        "sklearn",
        "torch",
    ]


def test_scan_project_dedupes_and_orders(tmp_path):
    project = tmp_path / "proj2"
    project.mkdir()
    (project / "module.py").write_text("import requests\nimport requests\nfrom pandas import DataFrame\n")
    (project / "another.py").write_text("from pandas.io import json\nimport requests\n")
    assert scan_project(str(project)) == ["pandas", "requests"]
