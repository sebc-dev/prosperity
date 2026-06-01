"""Unit tests for `budget.domain.CycleDetector` (S06.2, P06.2.1).

The detector is the **pure** core of category re-parenting: it decides whether
setting `node_id`'s parent to `new_parent_id` would close a cycle in the
unbounded tree, given an injected `get_parent` lookup. It imports only the
stdlib (no session / ORM / FastAPI), so the whole rule-set is testable with an
in-memory `dict.get`, and the invariants are pinned with Hypothesis
(domain-only, per Stratégie §4.2).

The Hypothesis properties verify post-mutation acyclicity with an algorithm
**independent** of the detector (a DFS three-colour back-edge check), never by
re-running `CycleDetector` — otherwise the property would merely restate the
implementation (anti-pattern Stratégie §12).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import hypothesis.strategies as st
import pytest
from hypothesis import assume, event, given

from backend.modules.budget.domain import (
    CategoryCycleError,
    CategoryError,
    CategoryNotFoundError,
    CycleDetector,
)

ParentLookup = Callable[[UUID], "UUID | None"]


def _lookup(mapping: dict[UUID, UUID | None]) -> ParentLookup:
    """Turn a `{child: parent}` dict into the injected `get_parent` callable."""
    return mapping.get


# ---------------------------------------------------------------------------
# Example-based — accepted shapes
# ---------------------------------------------------------------------------


def test_root_parent_always_accepted() -> None:
    # new_parent_id=None → re-parent to root → never a cycle (criterion #4).
    CycleDetector.detect_cycle(node_id=uuid4(), new_parent_id=None, get_parent=lambda _: None)


def test_move_to_unrelated_node_accepted() -> None:
    # Two disjoint subtrees: A→B and X→Y. Moving B under Y is fine.
    a, b, x, y = uuid4(), uuid4(), uuid4(), uuid4()
    chain = _lookup({b: a, a: None, y: x, x: None})
    CycleDetector.detect_cycle(node_id=b, new_parent_id=y, get_parent=chain)


def test_move_to_own_ancestor_accepted() -> None:
    # A→B→C (C child of B child of A). Moving C up under A (already its
    # grand-parent) is a legitimate re-parent, not a cycle.
    a, b, c = uuid4(), uuid4(), uuid4()
    chain = _lookup({c: b, b: a, a: None})
    CycleDetector.detect_cycle(node_id=c, new_parent_id=a, get_parent=chain)


def test_move_child_to_sibling_accepted() -> None:
    # Lateral reorg: under root R live A and B; move B under A.
    r, a, b = uuid4(), uuid4(), uuid4()
    chain = _lookup({a: r, b: r, r: None})
    CycleDetector.detect_cycle(node_id=b, new_parent_id=a, get_parent=chain)


def test_unknown_parent_treated_as_root() -> None:
    # get_parent returns None for an id absent from the map (create with a
    # parent that has no ancestors loaded yet) → walk terminates → OK.
    node, parent = uuid4(), uuid4()
    CycleDetector.detect_cycle(node_id=node, new_parent_id=parent, get_parent=lambda _: None)


# ---------------------------------------------------------------------------
# Example-based — rejected shapes
# ---------------------------------------------------------------------------


def test_direct_self_reference_rejected() -> None:
    node = uuid4()
    with pytest.raises(CategoryCycleError):
        CycleDetector.detect_cycle(node_id=node, new_parent_id=node, get_parent=lambda _: None)


def test_direct_child_becomes_parent_rejected() -> None:
    # ⚠️ Delta corrigé: A→B (B child of A); moving A under B closes A→B→A.
    a, b = uuid4(), uuid4()
    chain = _lookup({b: a, a: None})
    with pytest.raises(CategoryCycleError):
        CycleDetector.detect_cycle(node_id=a, new_parent_id=b, get_parent=chain)


def test_transitive_ancestor_rejected() -> None:
    # A→B→C; moving A under C: walking C's ancestors reaches B then A → cycle.
    a, b, c = uuid4(), uuid4(), uuid4()
    chain = _lookup({c: b, b: a, a: None})
    with pytest.raises(CategoryCycleError):
        CycleDetector.detect_cycle(node_id=a, new_parent_id=c, get_parent=chain)


def test_deep_transitive_ancestor_rejected() -> None:
    # Six-level chain n0→n1→…→n5; move the root n0 under the leaf n5 → cycle.
    nodes = [uuid4() for _ in range(6)]
    mapping: dict[UUID, UUID | None] = {nodes[0]: None}
    for child, parent in zip(nodes[1:], nodes[:-1], strict=True):
        mapping[child] = parent
    with pytest.raises(CategoryCycleError):
        CycleDetector.detect_cycle(
            node_id=nodes[0], new_parent_id=nodes[5], get_parent=_lookup(mapping)
        )


# ---------------------------------------------------------------------------
# Termination on a corrupted tree (criterion #5)
# ---------------------------------------------------------------------------


def test_corrupted_tree_terminates() -> None:
    # get_parent is cyclic ({x: y, y: x}) but does NOT contain node → the
    # visited-set guard breaks the walk; detect_cycle returns (no infinite
    # loop), and since node is unrelated the move is accepted.
    node, x, y = uuid4(), uuid4(), uuid4()
    chain = _lookup({x: y, y: x})
    CycleDetector.detect_cycle(node_id=node, new_parent_id=x, get_parent=chain)


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


def test_leaf_errors_subclass_base() -> None:
    # The S06.3 route maps the whole family with one `except CategoryError`.
    for leaf in (CategoryCycleError, CategoryNotFoundError):
        assert issubclass(leaf, CategoryError)


# ---------------------------------------------------------------------------
# Property-based (Hypothesis, inline strategies — shared strategy lands S06.4)
# ---------------------------------------------------------------------------


@st.composite
def _acyclic_tree(draw: st.DrawFn, *, max_nodes: int = 8) -> dict[UUID, UUID | None]:
    """Generate `{node: parent}` for an acyclic forest, by construction.

    Emit `n` node ids in order; each node points to `None` (a root) or to an
    **already-emitted** id. Pointing only backwards makes a cycle impossible
    (gabarit « parent ∈ {None} ∪ ids déjà émis », note issue).
    """
    n = draw(st.integers(min_value=1, max_value=max_nodes))
    ids = [uuid4() for _ in range(n)]
    mapping: dict[UUID, UUID | None] = {}
    for i, node in enumerate(ids):
        parent = draw(st.sampled_from([None, *ids[:i]])) if i else None
        mapping[node] = parent
    return mapping


def _is_acyclic(mapping: dict[UUID, UUID | None]) -> bool:
    """True iff the functional graph `{node: parent}` is acyclic.

    Independent of `CycleDetector`: a three-colour DFS over parent edges,
    flagging a back-edge (grey node re-entered) as a cycle. Never re-uses the
    detector's `visited` walk — so the property tests the invariant, not the
    implementation (Tests-F2).
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(mapping, WHITE)

    def visit(node: UUID) -> bool:
        colour[node] = GREY
        parent = mapping.get(node)
        if parent is not None and parent in colour:
            if colour[parent] == GREY:
                return False
            if colour[parent] == WHITE and not visit(parent):
                return False
        colour[node] = BLACK
        return True

    return all(colour[node] != WHITE or visit(node) for node in mapping)


def _descendants(mapping: dict[UUID, UUID | None], root: UUID) -> set[UUID]:
    """All nodes whose ancestor chain passes through `root` (root excluded)."""
    out: set[UUID] = set()
    for node in mapping:
        current = mapping.get(node)
        seen: set[UUID] = set()
        while current is not None and current not in seen:
            if current == root:
                out.add(node)
                break
            seen.add(current)
            current = mapping.get(current)
    return out


@given(data=st.data())
def test_property_accepted_mutation_keeps_tree_acyclic(data: st.DataObject) -> None:
    # ∀ valid tree + ∀ accepted mutation (node, new_parent): applying it keeps
    # the tree acyclic, verified by the INDEPENDENT DFS checker. Bias toward
    # non-trivial accepted moves: pick new_parent among non-descendants of node
    # (excluding node itself), so the "accepted → applied → re-checked" branch
    # actually bites (Tests-F2 anti-vacuity).
    mapping = data.draw(_acyclic_tree())
    nodes = list(mapping)
    node = data.draw(st.sampled_from(nodes))
    forbidden = _descendants(mapping, node) | {node}
    candidates = [None, *[n for n in nodes if n not in forbidden]]
    new_parent = data.draw(st.sampled_from(candidates))

    # The detector must accept this move (new_parent is None or a non-descendant).
    CycleDetector.detect_cycle(node_id=node, new_parent_id=new_parent, get_parent=mapping.get)
    event("applied non-root move" if new_parent is not None else "applied root move")

    mutated = dict(mapping)
    mutated[node] = new_parent
    assert _is_acyclic(mutated)


@given(node=st.uuids(), tree=_acyclic_tree())
def test_property_self_reference_always_rejected(node: UUID, tree: dict[UUID, UUID | None]) -> None:
    # ∀ node, ∀ tree: setting a node as its own parent is always a cycle.
    with pytest.raises(CategoryCycleError):
        CycleDetector.detect_cycle(node_id=node, new_parent_id=node, get_parent=tree.get)


@given(
    node=st.uuids(),
    new_parent=st.uuids(),
    edges=st.dictionaries(st.uuids(), st.uuids() | st.none(), max_size=12),
)
def test_property_walk_always_terminates(
    node: UUID, new_parent: UUID, edges: dict[UUID, UUID | None]
) -> None:
    # ∀ arbitrary (possibly cyclic) parent map: detect_cycle returns or raises
    # in finite time — never loops (pins the visited-set guard independently of
    # tree structure). assume node not reachable-from-itself-trivially is not
    # needed: either outcome (raise / return) is acceptable here.
    assume(new_parent != node)  # exercise the walk, not the early self-ref branch
    try:
        CycleDetector.detect_cycle(node_id=node, new_parent_id=new_parent, get_parent=edges.get)
    except CategoryCycleError:
        pass  # a detected cycle is a valid terminating outcome
