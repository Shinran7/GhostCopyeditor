"""The session hook uses the same 85% branch-coverage bar as the gate."""

from tests.branch_gate import BRANCH_COVERAGE_MIN
from tests.conftest import BRANCH_COVERAGE_MIN as HOOK_MIN


def test_conftest_uses_the_branch_coverage_bar() -> None:
    assert HOOK_MIN == BRANCH_COVERAGE_MIN == 85.0
