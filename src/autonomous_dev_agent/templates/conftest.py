"""Pytest configuration and shared fixtures."""
import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the async backend."""
    return "asyncio"


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for tests."""
    return tmp_path


# Add any shared fixtures here that tests across the project can use
