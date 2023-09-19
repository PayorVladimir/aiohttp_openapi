import logging

import pytest

pytest_plugins = ["aiohttp.pytest_plugin"]


@pytest.fixture(autouse=True)
def enable_logger():
    """Make log records visible in pytest report."""
    logger = logging.getLogger("aiohttp_openapi")
    logger.setLevel(logging.DEBUG)


@pytest.fixture(autouse=True)
def raise_if_warning_log(caplog, enable_logger):
    """Make log records visible in pytest report."""
    caplog.set_level(logging.WARNING)
    yield
    for when in ("setup", "call"):
        records = [
            r
            for r in caplog.get_records(when)
            if (r.levelno >= logging.WARNING) and (r.name.startswith("aiohttp_openapi"))
        ]
        if records:
            pytest.xfail(
                f"warning or error messages encountered during testing: {len(records)} "
            )
