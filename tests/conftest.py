"""
Pytest configuration — register custom markers and shared fixtures.
"""
import pytest


def pytest_configure(config):
    """Register custom markers to avoid warnings."""
    config.addinivalue_line(
        "markers", "integration: marks tests that hit live APIs (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers", "playwright: marks tests that require Playwright/Chromium"
    )
