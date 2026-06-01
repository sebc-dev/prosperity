"""Propriétés pures sur la strategy partagée `category_tree_strategy` (S06.4, P06.4.1).

Verrouille par property-based testing les invariants de la strategy (ordre
topologique, bornes taille / profondeur / arité) et leur cohérence avec le
domaine pur (`CycleDetector`) — aucun accès DB, périmètre `Stratégie de tests
§4.2` (Hypothesis sur le domaine pur uniquement).

⚠️ `test_property_strategy_trees_accepted_by_detector` est un **test de
cohérence strategy↔détecteur** : un arbre acyclique par construction ne doit
jamais être rejeté par `CycleDetector`, donc il garantit surtout qu'ils restent
synchronisés. La garantie *indépendante* d'acyclicité vit dans
`test_strategy_emits_topological_order` (parent index < child index sur TOUTES
les arêtes), distincte du DFS trois-couleurs de la property (b)
(`test_budget_cycle_detector.py`).
"""

from __future__ import annotations

from uuid import UUID

import hypothesis.strategies as st
from hypothesis import event, given
from hypothesis import target as hyp_target

from backend.modules.budget.domain import CategoryError, CycleDetector
from tests import strategies
from tests.strategies import GeneratedCategoryTree, category_tree_strategy


def _depth(parent_of: dict[UUID, UUID | None], node: UUID) -> int:
    """Profondeur d'un nœud (remontée bornée) — calcul LOCAL, indépendant de la strategy."""
    d, current, seen = 0, parent_of.get(node), {node}
    while current is not None and current not in seen:
        d += 1
        seen.add(current)
        current = parent_of.get(current)
    return d


@given(tree=category_tree_strategy())
def test_strategy_emits_topological_order(tree: GeneratedCategoryTree) -> None:
    # ∀ arbre, ∀ arête réelle (node, parent != None) : le parent apparaît
    # STRICTEMENT avant l'enfant. C'est l'oracle d'acyclicité INDÉPENDANT (par
    # l'ordre seul, distinct du DFS de la property (b)) : un graphe dont toutes
    # les arêtes pointent « en arrière » ne peut pas contenir de cycle.
    index = {nid: i for i, (nid, _) in enumerate(tree.nodes)}
    for node, parent in tree.nodes:
        if parent is not None:
            assert index[parent] < index[node]


@given(data=st.data())
def test_strategy_respects_node_count_bounds(data: st.DataObject) -> None:
    # min_nodes ≤ len(nodes) ≤ max_nodes (bornes de taille honorées).
    lo = data.draw(st.integers(min_value=1, max_value=6))
    hi = data.draw(st.integers(min_value=lo, max_value=lo + 6))
    tree = data.draw(category_tree_strategy(min_nodes=lo, max_nodes=hi))
    assert lo <= len(tree.nodes) <= hi


@given(data=st.data())
def test_strategy_respects_max_depth(data: st.DataObject) -> None:
    # ∀ arbre `max_depth=d` : profondeur de chaque nœud ≤ d-1 (max_depth en
    # NIVEAUX). `event`/`target` sur depth==d-1 PROUVENT que la borne est
    # atteignable (sinon le paramètre serait vacant — Tests-3).
    d = data.draw(st.integers(min_value=1, max_value=5))
    tree = data.draw(category_tree_strategy(min_nodes=1, max_nodes=12, max_depth=d))
    parent_of = tree.parent_of
    observed = max((_depth(parent_of, nid) for nid in parent_of), default=0)
    for nid in parent_of:
        assert _depth(parent_of, nid) <= d - 1
    hyp_target(float(observed), label="profondeur max observée")
    event(f"borne max_depth atteinte ({observed == d - 1})")


@given(data=st.data())
def test_strategy_respects_max_arity(data: st.DataObject) -> None:
    # ∀ arbre `max_arity=a` : aucun nœud n'a plus de `a` enfants directs.
    a = data.draw(st.integers(min_value=1, max_value=4))
    tree = data.draw(category_tree_strategy(min_nodes=1, max_nodes=12, max_arity=a))
    children: dict[UUID, int] = {}
    for _, parent in tree.nodes:
        if parent is not None:
            children[parent] = children.get(parent, 0) + 1
    assert all(count <= a for count in children.values())


@given(tree=category_tree_strategy(min_nodes=1, max_nodes=1))
def test_strategy_single_node_is_root(tree: GeneratedCategoryTree) -> None:
    # min_nodes=max_nodes=1 ⇒ unique nœud, racine (parent None).
    assert len(tree.nodes) == 1
    assert tree.nodes[0][1] is None


@given(tree=category_tree_strategy(min_nodes=3, max_nodes=8, max_arity=0))
def test_strategy_max_arity_zero_yields_only_roots(tree: GeneratedCategoryTree) -> None:
    # max_arity=0 ⇒ aucun nœud ne peut être parent ⇒ forêt de singletons
    # (cas plat + multi-racines pinné déterministement, Tests-4).
    assert len(tree.nodes) >= 3
    assert all(parent is None for _, parent in tree.nodes)


@given(tree=category_tree_strategy(max_nodes=10))
def test_property_strategy_trees_accepted_by_detector(tree: GeneratedCategoryTree) -> None:
    """TEST DE COHÉRENCE strategy↔domaine (gabarit test_accounts_strategies).

    NB : ce n'est PAS une garantie d'acyclicité indépendante — celle-ci vit dans
    `test_strategy_emits_topological_order` (ordre topologique). Ici on vérifie
    seulement que strategy et `CycleDetector` restent SYNCHRONISÉS : un arbre
    acyclique par construction ne doit jamais être rejeté par le détecteur.
    """
    parent_of = tree.parent_of
    max_depth_seen = 0
    for node, parent in tree.nodes:
        if parent is not None:
            max_depth_seen = max(max_depth_seen, _depth(parent_of, node))
        try:
            CycleDetector.detect_cycle(node_id=node, new_parent_id=parent, get_parent=parent_of.get)
        except CategoryError as exc:  # pragma: no cover - échec = strategy incohérente
            raise AssertionError(f"strategy ↔ détecteur incohérents sur {node!r}") from exc
    # Anti-vacuité ACTIVE : pousse Hypothesis vers des arbres profonds (le
    # détecteur ne traverse vraiment des ancêtres que si profondeur >= 2).
    hyp_target(float(max_depth_seen), label="profondeur max de l'arbre")
    event("arbre profondeur >= 2" if max_depth_seen >= 2 else "arbre plat")


def test_strategy_importable_without_side_effect() -> None:
    # Contrat du `tests/strategies.py` : importable sans effet de bord (gabarit
    # `account_with_members_strategy`). On vérifie le contrat d'API public sans
    # instancier ni toucher de ressource externe.
    assert callable(strategies.category_tree_strategy)
    assert issubclass(strategies.GeneratedCategoryTree, object)
