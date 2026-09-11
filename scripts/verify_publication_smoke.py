# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The consumer smoke test half of `poe verify-publication` — "resolves and installs" is not the
bar; "an adopter's day one traces" is (mirrors `verify-publication-smoke.ts` and the .NET
`RunConsumerSmokeTest`/java `run_smoke_test`).

Two tiers, run independently, because this release is a real, honest partial one (see
`verify_publication_registry.py`'s module docstring):

- **`run_core_recipe_smoke_test`** — the README's ["Try it locally"](../README.md#try-it-locally)
  recipe: `uv add narrativetrace` then `trace_object` + `MarkdownRenderer` directly, no framework.
  Only `narrativetrace` itself is required, so this tier runs on every release from 0.1.0 onward.
- **`run_pytest_plugin_smoke_test`** — the fully-documented
  [`first-10-minutes.md`](../documentation/first-10-minutes.md) / README ["Add it to one
  test"](../README.md#add-it-to-one-test) recipe: the `narrativetrace-pytest` fixture, real
  pytest11 auto-registration, `NARRATIVETRACE_OUTPUT=1`, and the exact frontmatter+call-flow
  Markdown the docs promise. `narrativetrace-pytest` (and its own dependency,
  `narrativetrace-glossary`) are not on PyPI yet — the caller (`verify_publication.py`) only calls
  this once its own presence poll has confirmed the package is actually there; skip that check and
  this tier fails on an ordinary `pip install` 404, which is a true statement but the wrong one —
  "not yet published" and "broken" must never look the same on the report.

Both tiers install from the REAL index into an isolated `uv`-managed venv with a throwaway cache
— never the ambient environment this repository's own `uv sync --all-packages` populated —
because the whole point is proving what a first-time adopter gets, not what is already warm on
this machine. `--no-config` keeps even a stray `uv.toml`/`pyproject.toml` `[tool.uv]` section from
this repository (or a parent directory) from leaking into either the install or the run.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - every call site below passes a fixed argv list, never a shell
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_INDEX_URL = "https://pypi.org/simple"
SUBPROCESS_TIMEOUT_SECONDS = 300

SmokeVerdict = Literal["PASSED", "FAILED", "SKIPPED"]


@dataclass(frozen=True)
class SmokeResult:
    tier: str
    verdict: SmokeVerdict
    detail: str


CORE_RECIPE_SCRIPT = """\
from narrativetrace import ContextVarNarrativeContext, MarkdownRenderer, trace_object


# OrderService is not repeated in the README's own "Try it locally" snippet -- it is the same
# class first-10-minutes.md step 2 defines, reused here rather than fabricated, so this remains
# the documented recipe, not a lookalike.
class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(MarkdownRenderer().render(context.capture_trace()))
"""

CORE_RECIPE_MUST_CONTAIN = (
    "OrderService.place_order",
    'customer_id: `"cust-1"`',
    'product_id: `"prod-42"`',
    "quantity: `3`",
    '`"ORD-cust-1-prod-42-3"`',
)

ORDER_SERVICE_MODULE = """\
class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
"""

ORDER_SERVICE_TEST_MODULE = """\
from narrativetrace import trace_object

from order_service import OrderService


class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
"""

# The exact promised content of documentation/first-10-minutes.md step 5 / README "Add it to one
# test" step 4 -- the assertion is "the docs are true", not "a file exists".
PYTEST_PLUGIN_TRACE_MUST_CONTAIN = (
    "entry_point: OrderService.place_order",
    "error_count: 0",
    '**OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`)'
    ' → `"ORD-C-1234-SKU-KB-2"`',
)


@dataclass(frozen=True)
class _RunOutcome:
    ok: bool
    stdout: str
    log: str


def _run(argv: Sequence[str], cwd: Path, env: dict[str, str]) -> _RunOutcome:
    result = subprocess.run(  # nosec B603 - argv is a fixed list built by this module, no shell
        list(argv),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    log = f"$ {' '.join(argv)}\n{result.stdout}\n{result.stderr}"
    return _RunOutcome(ok=result.returncode == 0, stdout=result.stdout, log=log)


def isolated_env() -> dict[str, str]:
    """Env for `uv`, the install, and the traced run: this process's own environment (so `PATH`
    still resolves `uv` itself) minus `VIRTUAL_ENV`, which would otherwise point `uv` at this
    repository's own workspace venv instead of the fresh one this module creates."""
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    return env


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _write_failure_log(work_dir: Path, log: str) -> None:
    (work_dir / "smoke-output.log").write_text(log, encoding="utf-8")


def _fresh_dirs(prefix: str) -> tuple[Path, Path]:
    work_dir = Path(tempfile.mkdtemp(prefix=f"nt-verify-publication-{prefix}-"))
    cache_dir = Path(tempfile.mkdtemp(prefix=f"nt-verify-publication-{prefix}-cache-"))
    return work_dir, cache_dir


def _venv_and_install(
    work_dir: Path, cache_dir: Path, env: dict[str, str], package_spec: str, index_url: str
) -> _RunOutcome:
    """Creates a fresh venv under `work_dir/.venv` and installs `package_spec` into it from
    `index_url`, both using `cache_dir` (never this machine's warm `uv` cache) — the install step
    only runs when the venv step succeeded, so a broken interpreter resolution never reads as a
    package-install failure."""
    venv_result = _run(
        [
            "uv",
            "venv",
            str(work_dir / ".venv"),
            "--python",
            "3.12",
            "--cache-dir",
            str(cache_dir),
            "--no-config",
        ],
        work_dir,
        env,
    )
    if not venv_result.ok:
        return venv_result
    return _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(_venv_python(work_dir / ".venv")),
            "--default-index",
            index_url,
            "--cache-dir",
            str(cache_dir),
            "--no-config",
            package_spec,
        ],
        work_dir,
        env,
    )


def _assert_contains(content: str, must_contain: Sequence[str]) -> str | None:
    missing = [needle for needle in must_contain if needle not in content]
    return f"missing: {' | '.join(missing)}" if missing else None


def run_core_recipe_smoke_test(version: str, index_url: str = DEFAULT_INDEX_URL) -> SmokeResult:
    """README "Try it locally": `uv add narrativetrace`, then `trace_object` + `MarkdownRenderer`
    directly -- no framework, no fixture, so this needs only `narrativetrace` itself."""
    tier = "core-recipe"
    work_dir, cache_dir = _fresh_dirs("core")
    env = isolated_env()
    install = _venv_and_install(work_dir, cache_dir, env, f"narrativetrace=={version}", index_url)
    if not install.ok:
        _write_failure_log(work_dir, install.log)
        return SmokeResult(tier, "FAILED", f"install failed — see {work_dir}/smoke-output.log")

    script = work_dir / "smoke_core_recipe.py"
    script.write_text(CORE_RECIPE_SCRIPT, encoding="utf-8")
    run = _run([str(_venv_python(work_dir / ".venv")), str(script)], work_dir, env)
    if not run.ok:
        _write_failure_log(work_dir, run.log)
        return SmokeResult(
            tier, "FAILED", f"recipe script failed — see {work_dir}/smoke-output.log"
        )

    problem = _assert_contains(run.stdout, CORE_RECIPE_MUST_CONTAIN)
    if problem:
        _write_failure_log(work_dir, run.log)
        return SmokeResult(
            tier, "FAILED", f"rendered output {problem} (see {work_dir}/smoke-output.log)"
        )

    return SmokeResult(
        tier, "PASSED", "install + the core trace_object/MarkdownRenderer recipe matched the docs"
    )


def run_pytest_plugin_smoke_test(version: str, index_url: str = DEFAULT_INDEX_URL) -> SmokeResult:
    """`documentation/first-10-minutes.md` / README "Add it to one test": install
    `narrativetrace-pytest`, write the exact `order_service.py` + test the docs show, run
    `NARRATIVETRACE_OUTPUT=1 pytest -s`, and assert the written Markdown matches what the docs
    promise on the lines that matter (frontmatter fields, the call-flow line).

    The caller is expected to have already confirmed `narrativetrace-pytest` is PRESENT at
    `version` — this function does not re-check; see the module docstring for why that gating
    lives one layer up, in `verify_publication.py`.
    """
    tier = "pytest-plugin-recipe"
    work_dir, cache_dir = _fresh_dirs("pytest")
    env = isolated_env()
    install = _venv_and_install(
        work_dir, cache_dir, env, f"narrativetrace-pytest=={version}", index_url
    )
    if not install.ok:
        _write_failure_log(work_dir, install.log)
        return SmokeResult(tier, "FAILED", f"install failed — see {work_dir}/smoke-output.log")

    (work_dir / "order_service.py").write_text(ORDER_SERVICE_MODULE, encoding="utf-8")
    (work_dir / "test_order_service.py").write_text(ORDER_SERVICE_TEST_MODULE, encoding="utf-8")
    run_env = dict(env)
    run_env["NARRATIVETRACE_OUTPUT"] = "1"
    run = _run([str(_venv_python(work_dir / ".venv")), "-m", "pytest", "-s"], work_dir, run_env)
    if not run.ok:
        _write_failure_log(work_dir, run.log)
        return SmokeResult(tier, "FAILED", f"pytest run failed — see {work_dir}/smoke-output.log")

    trace_file = (
        work_dir
        / "narrative-traces"
        / "traces"
        / "TestOrderService"
        / "test_customer_places_order.md"
    )
    if not trace_file.is_file():
        return SmokeResult(tier, "FAILED", f"pytest passed but no trace file at {trace_file}")

    content = trace_file.read_text(encoding="utf-8")
    problem = _assert_contains(content, PYTEST_PLUGIN_TRACE_MUST_CONTAIN)
    if problem:
        return SmokeResult(tier, "FAILED", f"{trace_file} {problem}")

    return SmokeResult(tier, "PASSED", f"install + pytest run matched the docs: {trace_file}")


def skipped_pytest_plugin_result(reason: str) -> SmokeResult:
    return SmokeResult("pytest-plugin-recipe", "SKIPPED", reason)
