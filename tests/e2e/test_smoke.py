"""E2E harness smoke test.

Validates the whole real-commit pipeline end to end from the e2e tier:
the `e2e` marker, `committed_client`, and `_clean_committed_db` all
resolve from the root conftest, and `GET /setup` answers 200 on a freshly
truncated database.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]


async def test_setup_probe_open_on_fresh_db(committed_client):
    resp = await committed_client.get("/setup")
    assert resp.status_code == 200
    assert resp.json() == {"status": "open"}
