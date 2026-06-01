"""Propriété Hypothesis sur la non-cascade de `archive_category` (S06.4, P06.4.1 c).

⚠️ EXCEPTION ASSUMÉE au périmètre `Stratégie de tests §4.2` (« pas d'Hypothesis
sur les services ») et à l'anti-pattern §12 (« Hypothesis sur une fonction qui
écrit en DB = flaky garanti ») — mandatée par l'issue #105 : l'invariant
« pas de cascade, pas de re-parentage automatique » (CONTEXT.md §Catégorie, D9)
est *quantifiable*, donc property-testé. La flakiness est neutralisée par
l'isolement strict du gabarit `test_accounts_rebalance_property.py` (S05.5 D5) :

  - le **socle** (schéma seul) est créé **une seule fois** par une fixture
    **module-scoped** — donc pas de `HealthCheck.function_scoped_fixture` ni de
    fuite d'état entre exemples. `Category` n'a AUCUNE FK externe
    (`household`/`users`), donc le socle se réduit au schéma : aucun seed ;
  - **chaque exemple** ouvre son propre engine via `asyncio.run`, seede l'arbre
    en ordre topologique (self-FK `RESTRICT` satisfaite par un seul flush) dans
    une transaction, et la **rollback** — rien ne persiste hors de l'exemple ;
  - `postgres_container` n'expose qu'une URL (string), partageable sans conflit.

Budget figé localement (`max_examples=25`, `deadline=None`) : le tier DB ne suit
volontairement pas le profil `nightly` (500 × engine = trop lent).

Hors scope (couvert ailleurs) : l'idempotence de l'archivage
(`test_archive_already_archived_returns_false`, S06.3), la concurrence du move
(`test_budget_move_concurrency.py`), et l'AuthZ des routes `/categories`
(`test_budget_routes_*`, example-based, httpx — aucune Hypothesis sur HTTP §4.2).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from hypothesis import target as hyp_target
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.modules.budget.models import Category
from backend.modules.budget.service.categories import archive_category
from backend.shared.models import Base
from tests.strategies import GeneratedCategoryTree, category_tree_strategy


@pytest.fixture(scope="module")
def archive_socle(postgres_container) -> Iterator[str]:
    """Schéma créé UNE fois, `drop_all` au teardown. Renvoie l'URL de connexion.

    Module-scoped (pas function-scoped) ⇒ aucun `HealthCheck.function_scoped_fixture`
    sur la ré-exécution Hypothesis. `Category` n'ayant aucune FK externe, le socle
    se limite au schéma — aucun seed (gabarit `rebalance_socle` sans household/users).
    Le `drop_all` empêche le schéma de fuiter sur les modules de test suivants qui
    partagent le même conteneur Postgres.
    """
    url = postgres_container.get_connection_url()

    async def _setup() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    async def _teardown() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_setup())
    yield url
    asyncio.run(_teardown())


@given(
    tree=category_tree_strategy(min_nodes=1, max_nodes=10, max_depth=4),
    data=st.data(),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_archive_never_cascades(
    archive_socle: str, tree: GeneratedCategoryTree, data: st.DataObject
) -> None:
    # ∀ arbre valide et ∀ nœud cible : archiver la cible (1) laisse archived_at
    # NULL sur TOUS les autres nœuds (non-cascade D9 + non-propagation) ET (2) ne
    # MODIFIE AUCUN parent_id (non-re-parentage automatique, CONTEXT.md §Catégorie).
    url = archive_socle
    target_id = data.draw(st.sampled_from(tree.ids))
    descendants = tree.descendants(target_id)  # oracle structurel, indépendant du service
    before_structure = {nid: pid for nid, pid in tree.nodes}  # parents attendus, inchangés
    # Anti-vacuité ACTIVE : pousse Hypothesis vers des cibles INTERNES (sinon
    # archiver une feuille ne prouve jamais la non-cascade).
    hyp_target(float(len(descendants)), label="descendants de la cible")
    event("cible interne (a des descendants)" if descendants else "cible feuille")

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                for node_id, parent_id in tree.nodes:  # ordre topologique ⇒ self-FK OK
                    s.add(Category(id=node_id, name="n", parent_id=parent_id))
                await s.flush()

                assert await archive_category(s, category_id=target_id) is True

                s.expire_all()
                rows = (
                    await s.execute(select(Category.id, Category.parent_id, Category.archived_at))
                ).all()
                archived = {r.id for r in rows if r.archived_at is not None}
                parents = {r.id: r.parent_id for r in rows}
                # (1) EXACTEMENT la cible archivée : ni cascade descendants, ni
                # propagation aux nœuds non liés.
                assert archived == {target_id}
                # (2) AUCUN re-parentage : structure des nœuds INTACTE (cible incluse).
                assert parents == before_structure
                await s.rollback()  # rien ne persiste hors de l'exemple
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_archive_noncascade_two_level_concrete(archive_socle: str) -> None:
    """Cas concret épinglé : racine → enfant → petit-enfant, archiver le milieu.

    `@example` ne peut pas fournir des valeurs tirées par `data.draw()`, donc le
    cas à 3 niveaux est verrouillé ici (gabarit `test_rebalance_50_50_to_30_70`,
    S05.5 D7). Asserte : l'enfant du milieu archivé, racine ET petit-enfant
    `archived_at IS NULL`, et tous les `parent_id` inchangés.
    """
    url = archive_socle
    root, child, grandchild = uuid4(), uuid4(), uuid4()
    tree = GeneratedCategoryTree(nodes=((root, None), (child, root), (grandchild, child)))

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                for node_id, parent_id in tree.nodes:
                    s.add(Category(id=node_id, name="n", parent_id=parent_id))
                await s.flush()

                assert await archive_category(s, category_id=child) is True

                s.expire_all()
                rows = (
                    await s.execute(select(Category.id, Category.parent_id, Category.archived_at))
                ).all()
                by_id = {r.id: r for r in rows}
                assert by_id[child].archived_at is not None
                assert by_id[root].archived_at is None
                assert by_id[grandchild].archived_at is None
                assert by_id[root].parent_id is None
                assert by_id[child].parent_id == root
                assert by_id[grandchild].parent_id == child
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())
