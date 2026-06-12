"""Reusable PowerSync Service testcontainer stack (S13.7, factored for S13.8/E14).

Boots the two halves of the sync infra the dev `compose.dev.yml` runs — a
logical-replication Postgres (source + a dedicated bucket-storage DB) and the
pinned `journeyapps/powersync-service` image — on a shared Docker network, with
the REAL `powersync/` config mounted, after `alembic upgrade head` + the initdb
roles/publication SQL. The download-flow visibility work (S13.8) and the upload
handler (E14) reuse this exact stack, so it lives here rather than inline in a
single test.

DEFERRED to S13.8 (needs the JWT download client this stack stubs out). The
following per-recipient stream assertions from the S13.7 plan are NOT covered
here and are owed once the authenticated client lands — they cannot be expressed
without observing a real download stream:
  - debtor stream lacks account_id/source_transaction_id; creditor's carries them
    (incl. the overflow case: real columns both sides, ADR 0003 consequences);
  - share_request source_transaction_id masked for `requested_from`, real for
    `requested_by`;
  - third party sees no debt; settlement_lines visible to debt participants only;
  - edge cases: archived personal account still syncs, revoked share_request
    still visible, shared budget routed by contributor (not account_id).
Until then masking rests on the structural pin (unit) + boot-time compilation.

Underscore prefix → pytest does not collect this as a test module.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from types import TracebackType
from urllib.error import URLError
from urllib.request import urlopen

import docker
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.postgres import PostgresContainer

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
INITDB = REPO_ROOT / "compose" / "initdb"
POWERSYNC_DIR = REPO_ROOT / "powersync"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Driver-safe initdb scripts (00 roles, 10 publication); 05 (CREATE DATABASE via
# \gexec) is psql-only, so the storage DB is created in Python here instead.
_INITDB_FILES = ("00_powersync_roles.sql", "10_powersync_publication.sql")
HOUSEHOLD_SINGLETON = "00000000-0000-0000-0000-000000000001"


def docker_available() -> bool:
    try:
        docker.from_env().ping()
    except Exception:
        return False
    return True


def _pinned_image_tag() -> str:
    """The pinned PowerSync image tag from .env.example (a manifest test forbids
    `latest`), so the test boots the same version compose.dev.yml runs."""
    for raw in ENV_EXAMPLE.read_text().splitlines():
        line = raw.strip()
        if line.startswith("PS_IMAGE_TAG="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("PS_IMAGE_TAG not declared in .env.example")


class PowerSyncStack:
    """Context manager owning the network, Postgres, and PowerSync containers."""

    def __init__(self) -> None:
        self._network: Network | None = None
        self._pg: PostgresContainer | None = None
        self._service: DockerContainer | None = None
        self._engine: Engine | None = None

    # -- lifecycle ----------------------------------------------------------
    def __enter__(self) -> PowerSyncStack:
        self._network = Network()
        self._network.create()
        self._pg = PostgresContainer(
            "postgres:17-alpine",
            driver="asyncpg",
            username="prosperity",
            password="prosperity",
            dbname="prosperity",
        )
        # wal_level=logical is a startup parameter — set via command so it is
        # effective on first boot (mirrors compose.dev.yml).
        self._pg.with_command(
            "postgres -c wal_level=logical -c max_wal_senders=10 "
            "-c max_replication_slots=10 -c wal_sender_timeout=0"
        )
        self._pg.with_network(self._network).with_network_aliases("postgres")
        self._pg.start()
        self._provision()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._engine is not None:
            self._engine.dispose()
        if self._service is not None:
            self._service.stop()
        if self._pg is not None:
            self._pg.stop()
        if self._network is not None:
            self._network.remove()

    # -- provisioning -------------------------------------------------------
    def _provision(self) -> None:
        assert self._pg is not None
        async_dsn = self._pg.get_connection_url()
        sync_dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

        # 1. App schema (the publication SQL is table-existence-guarded).
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", async_dsn)
        command.upgrade(cfg, "head")

        self._engine = create_engine(sync_dsn)
        # 2. initdb roles + publication, then set the dev passwords the source URI
        #    expects (the scripts create the roles without a fixed password here).
        raw = self._engine.raw_connection()
        try:
            cursor = raw.cursor()
            for name in _INITDB_FILES:
                cursor.execute((INITDB / name).read_text())
            cursor.execute("ALTER ROLE powersync PASSWORD 'powersync_dev'")
            cursor.execute("ALTER ROLE ps_storage PASSWORD 'ps_storage_dev'")
            raw.commit()
        finally:
            raw.close()

        # 3. Dedicated bucket-storage DB (05 is psql-only \gexec — do it here).
        autocommit = create_engine(sync_dsn, isolation_level="AUTOCOMMIT")
        with autocommit.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'powersync_storage'")
            ).first()
            if not exists:
                conn.exec_driver_sql("CREATE DATABASE powersync_storage OWNER ps_storage")
        autocommit.dispose()

    # -- seeding ------------------------------------------------------------
    def seed_personal_share_request_debt(self) -> dict[str, str]:
        """Seed a household, two users, a personal account owned by the creditor,
        a source transaction, a share_request, and the materialised debt
        (debtor → creditor). Returns the ids."""
        assert self._engine is not None
        ids = {k: str(uuid.uuid4()) for k in ("creditor", "debtor", "account", "tx", "sr", "debt")}
        with self._engine.begin() as conn:
            conn.execute(
                text("INSERT INTO household (id, name, base_currency) VALUES (:i, 'H', 'EUR')"),
                {"i": HOUSEHOLD_SINGLETON},
            )
            for key, name in (("creditor", "Alice"), ("debtor", "Bob")):
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, display_name, role) "
                        "VALUES (:i, :e, 'x', :n, 'member')"
                    ),
                    {"i": ids[key], "e": f"{ids[key]}@example.test", "n": name},
                )
            conn.execute(
                text(
                    "INSERT INTO accounts (id, household_id, name, type, currency, owner_id) "
                    "VALUES (:i, :h, 'Perso', 'courant', 'EUR', :o)"
                ),
                {"i": ids["account"], "h": HOUSEHOLD_SINGLETON, "o": ids["creditor"]},
            )
            conn.execute(
                text(
                    "INSERT INTO transactions "
                    "(id, account_id, date, state, created_by, tags, debt_generation_override) "
                    "VALUES (:i, :a, CURRENT_DATE, 'confirmed', :u, '{}', 'default')"
                ),
                {"i": ids["tx"], "a": ids["account"], "u": ids["creditor"]},
            )
            conn.execute(
                text(
                    "INSERT INTO share_requests "
                    "(id, source_transaction_id, requested_by, requested_from, ratio, short_label) "
                    "VALUES (:i, :t, :by, :frm, 0.5, 'Dinner')"
                ),
                {"i": ids["sr"], "t": ids["tx"], "by": ids["creditor"], "frm": ids["debtor"]},
            )
            conn.execute(
                text(
                    "INSERT INTO debts (id, from_user_id, to_user_id, amount_cents, currency, "
                    "account_id, source_transaction_id, origin, share_ratio) "
                    "VALUES (:i, :frm, :to, 1000, 'EUR', :a, :t, 'personal_share_request', 0.5)"
                ),
                {
                    "i": ids["debt"],
                    "frm": ids["debtor"],
                    "to": ids["creditor"],
                    "a": ids["account"],
                    "t": ids["tx"],
                },
            )
        return ids

    # -- service ------------------------------------------------------------
    def start_service(self) -> None:
        assert self._network is not None
        service = DockerContainer(f"journeyapps/powersync-service:{_pinned_image_tag()}")
        service.with_network(self._network)
        env = {
            "POWERSYNC_CONFIG_PATH": "/config/config.yaml",
            "NODE_OPTIONS": "--max-old-space-size=1000",
            "PS_PORT": "8080",
            "PS_SOURCE_URI": "postgresql://powersync:powersync_dev@postgres:5432/prosperity",
            "PS_STORAGE_URI": "postgresql://ps_storage:ps_storage_dev@postgres:5432/powersync_storage",
            # Client JWT auth (JWKS) is exercised in S13.8; boot/replication does
            # not fetch it. A dummy URL keeps the config valid.
            "PS_JWKS_URI": "http://postgres:5432/unused-jwks.json",
            "PS_ADMIN_TOKEN": "dev_admin_token",
            "PS_LOG_LEVEL": "info",
        }
        for key, value in env.items():
            service.with_env(key, value)
        service.with_command("start -r unified")
        service.with_volume_mapping(str(POWERSYNC_DIR), "/config", "ro")
        service.with_exposed_ports(8080)
        service.start()
        self._service = service

    def _probe(self, path: str) -> bool:
        assert self._service is not None
        host = self._service.get_container_host_ip()
        port = self._service.get_exposed_port(8080)
        try:
            return urlopen(f"http://{host}:{port}{path}", timeout=3).status == 200
        except (URLError, OSError):
            return False

    def wait_until_ready(self, timeout: int = 180) -> bool:
        """Poll /probes/readiness until 200 or timeout. Readiness reflects the
        replicator reaching a consistent checkpoint over every published table."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._probe("/probes/readiness"):
                return True
            time.sleep(2)
        return False

    def wait_for_log(self, marker: str, timeout: int = 30) -> bool:
        """Poll the service logs until `marker` appears or `timeout` elapses.

        Deterministic replacement for a fixed `sleep`: replication markers land a
        little after readiness, so callers that grep the logs wait on the marker
        itself rather than guessing a delay (flaky under CI load)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker in self.service_logs():
                return True
            time.sleep(1)
        return False

    def service_logs(self) -> str:
        assert self._service is not None
        return b"".join(self._service.get_logs()).decode(errors="replace")
