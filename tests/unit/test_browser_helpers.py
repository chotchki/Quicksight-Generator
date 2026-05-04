"""Unit tests for ``common/browser/helpers.py``.

W.4 — ``get_user_arn`` historically silently fell back to a
hardcoded account-specific ARN when ``QS_E2E_USER_ARN`` was unset.
That masked CI misconfiguration (Phase W's ``ci-bot`` has a
different ARN — the fallback produced an embed URL the bot
couldn't view) and burned a project account ID into the source.
The contract is now: env var unset = ``RuntimeError`` at the call
site, fail loud.
"""

from __future__ import annotations

import re

import pytest

from quicksight_gen.common.browser.helpers import (
    _test_id_from_pytest_env,
    get_user_arn,
)


class TestGetUserArn:
    def test_returns_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv(
            "QS_E2E_USER_ARN",
            "arn:aws:quicksight:us-east-1:111122223333:user/default/test-user",
        )
        assert get_user_arn() == (
            "arn:aws:quicksight:us-east-1:111122223333:user/default/test-user"
        )

    def test_raises_when_env_var_unset(self, monkeypatch):
        monkeypatch.delenv("QS_E2E_USER_ARN", raising=False)
        with pytest.raises(RuntimeError, match="QS_E2E_USER_ARN is not set"):
            get_user_arn()

    def test_raises_when_env_var_empty_string(self, monkeypatch):
        # An empty string is treated as unset — same fail-loud path.
        # Otherwise an unset-via-``export QS_E2E_USER_ARN=`` shell
        # idiom would slip through with an empty UserArn that AWS
        # rejects with a less obvious error.
        monkeypatch.setenv("QS_E2E_USER_ARN", "")
        with pytest.raises(RuntimeError, match="QS_E2E_USER_ARN is not set"):
            get_user_arn()

    def test_error_message_points_at_e2e_setup_runbook(self, monkeypatch):
        # The runbook reference is the documented path for fixing
        # this in CI; if the doc moves, this test fails loud and
        # reminds the editor to update the message.
        monkeypatch.delenv("QS_E2E_USER_ARN", raising=False)
        with pytest.raises(RuntimeError) as exc_info:
            get_user_arn()
        assert ".github/E2E_SETUP.md" in str(exc_info.value)


class TestTestIdFromPytestEnv:
    """X.1.a — auto-failure-screenshot hook derives a filename-safe
    test ID from ``PYTEST_CURRENT_TEST`` so each failing test gets a
    distinct screenshot in ``_failures/<test_id>.png``."""

    def test_strips_phase_suffix(self):
        assert _test_id_from_pytest_env(
            "tests/e2e/test_foo.py::test_bar (call)"
        ) == "tests_e2e_test_foo__test_bar"

    def test_handles_setup_and_teardown_phases(self):
        # Failures during fixture setup / teardown also produce sensible
        # filenames — same test_id regardless of phase, so the latest
        # snapshot wins (acceptable; setup/teardown failures are rare
        # and call-phase is the common case anyway).
        assert _test_id_from_pytest_env(
            "tests/e2e/test_foo.py::test_bar (setup)"
        ) == "tests_e2e_test_foo__test_bar"

    def test_handles_parametrized_test(self):
        # Parametrization brackets ``[case_x]`` stay in the filename —
        # they're filename-safe on Linux/macOS and disambiguate
        # different parameter sets that fail in the same run.
        assert _test_id_from_pytest_env(
            "tests/e2e/test_foo.py::test_bar[case_x] (call)"
        ) == "tests_e2e_test_foo__test_bar[case_x]"

    def test_handles_class_based_test(self):
        assert _test_id_from_pytest_env(
            "tests/e2e/test_foo.py::TestFoo::test_bar (call)"
        ) == "tests_e2e_test_foo__TestFoo__test_bar"

    def test_returns_unknown_when_env_var_unset(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert _test_id_from_pytest_env() == "unknown"

    def test_returns_unknown_when_env_var_empty(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "")
        assert _test_id_from_pytest_env() == "unknown"

    def test_reads_env_var_when_no_arg_supplied(self, monkeypatch):
        monkeypatch.setenv(
            "PYTEST_CURRENT_TEST",
            "tests/foo.py::bar (call)",
        )
        assert _test_id_from_pytest_env() == "tests_foo__bar"


class TestNoHardcodedArnInSource:
    """W.4 hygiene: the helpers module must not retain a hardcoded
    AWS account ID. The previous silent fallback baked a real account
    ID into source — this test guards against regression."""

    def test_no_aws_account_id_literal_in_helpers_module(self) -> None:
        from quicksight_gen.common.browser import helpers as helpers_mod
        from pathlib import Path

        source = Path(helpers_mod.__file__).read_text()
        # Any 12-digit run that looks like an AWS account ID inside
        # an ARN string. Tightened to ``arn:`` context so we don't
        # false-positive on, e.g., timeouts or unrelated digit runs.
        matches = re.findall(r"arn:aws:[^\s\"]+:\d{12}:", source)
        assert not matches, (
            f"helpers.py contains hardcoded ARN(s) with embedded "
            f"AWS account IDs: {matches}. Read the user ARN from "
            f"``QS_E2E_USER_ARN`` instead."
        )
