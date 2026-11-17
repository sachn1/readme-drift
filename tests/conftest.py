"""Shared pytest fixtures for the readme-drift test suite."""

import pytest

from readme_drift.tips import NO_TIPS_ENV


@pytest.fixture(autouse=True)
def _no_first_use_tips(monkeypatch):
    """Keep onboarding tips (and their cache marker) out of unrelated tests."""
    monkeypatch.setenv(NO_TIPS_ENV, "1")
