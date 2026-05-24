"""Smoke tests proving pytest + pytest-asyncio wiring works."""

import asyncio


def test_pytest_collects_unit_tests() -> None:
    assert 1 + 1 == 2


async def test_pytest_asyncio_runs_coroutines() -> None:
    await asyncio.sleep(0)
    assert True
