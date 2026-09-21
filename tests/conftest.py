"""Enforce the project's branch-coverage requirement at the end of a test run."""

from __future__ import annotations

from typing import Any

import pytest

from tests.branch_gate import BRANCH_COVERAGE_MIN, branch_coverage_failed, branch_percent


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtestloop(session: pytest.Session) -> Any:
    """Run tests, then fail the session if branch coverage is under 85%."""
    result = yield
    if hasattr(session.config, "workerinput"):
        return result
    pluginmanager = session.config.pluginmanager
    if not pluginmanager.hasplugin("_cov"):
        return result
    plugin = pluginmanager.getplugin("_cov")
    if plugin is None or plugin._disabled or plugin.cov_controller is None:
        return result
    percent = branch_percent(plugin.cov_controller.cov)
    failed = branch_coverage_failed(percent)
    session.config._branch_coverage_percent = percent  # type: ignore[attr-defined]
    session.config._branch_coverage_failed = failed  # type: ignore[attr-defined]
    if failed:
        session.testsfailed += 1
    return result


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Print the branch-coverage result under the coverage table."""
    config = terminalreporter.config
    if not hasattr(config, "_branch_coverage_percent"):
        return
    percent = config._branch_coverage_percent
    failed = config._branch_coverage_failed
    shown = "not measured" if percent is None else f"{percent:.2f}%"
    message = (
        f"{'FAIL ' if failed else ''}"
        f"Required branch coverage of {BRANCH_COVERAGE_MIN:.0f}% "
        f"{'not reached' if failed else 'reached'}. "
        f"Branch coverage: {shown}\n"
    )
    terminalreporter.write(message, **({"red": True, "bold": True} if failed else {"green": True}))
