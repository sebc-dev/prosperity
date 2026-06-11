"""(Dé)sérialisation + validation de l'enveloppe batch PowerSync (S13.2 / P13.2.3).

Schemas PURS (aucune logique métier, D8) : on teste la FORME du contrat wire —
round-trip (exemple + property Hypothesis), rejet des `op`/UUID mal formés,
`extra="forbid"` sur l'enveloppe mais payload opaque, bornes anti-DoS (cardinalité
du batch, longueur de `table`), et la forme figée `WriteError`/`WriteResult`.
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given
from pydantic import ValidationError

from backend.modules.sync.schemas import (
    _MAX_MUTATIONS,  # pyright: ignore[reportPrivateUsage]  # borne anti-DoS épinglée par le test
    _MAX_TABLE_NAME,  # pyright: ignore[reportPrivateUsage]
    BatchUpload,
    Mutation,
    WriteError,
    WriteResult,
)
from tests.strategies import batch_upload_strategy


def _mutation(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "client_request_id": str(uuid.uuid4()),
        "table": "transactions",
        "op": "insert",
        "payload": {"amount_cents": 1000, "currency": "EUR"},
    }
    base.update(overrides)
    return base


# --- round-trip ------------------------------------------------------------


def test_batch_round_trip_example() -> None:
    """Un batch bien formé (2 mutations insert/update) → dump → validate identique."""
    batch = BatchUpload(
        mutations=[
            Mutation.model_validate(_mutation(op="insert")),
            Mutation.model_validate(_mutation(op="update", table="accounts")),
        ]
    )
    assert BatchUpload.model_validate(batch.model_dump()) == batch


@given(batch_upload_strategy())
def test_batch_round_trip_property(batch: BatchUpload) -> None:
    """`model_validate(b.model_dump()) == b` sur des UUID/payloads/cardinalités
    arbitraires (schemas purs, §4.2) — attrape ce que les exemples manquent."""
    assert BatchUpload.model_validate(batch.model_dump()) == batch


def test_write_result_round_trip() -> None:
    """Symétrie des 3 schemas : `WriteResult` (succès + échec) round-trip aussi."""
    ok = WriteResult(client_request_id=uuid.uuid4(), success=True)
    ko = WriteResult(
        client_request_id=uuid.uuid4(),
        success=False,
        error=WriteError(code="validation_error", message="bad payload"),
        server_values={"id": str(uuid.uuid4())},
    )
    assert WriteResult.model_validate(ok.model_dump()) == ok
    assert WriteResult.model_validate(ko.model_dump()) == ko


# --- validation : Mutation -------------------------------------------------


def test_invalid_op_rejected() -> None:
    with pytest.raises(ValidationError):
        Mutation.model_validate(_mutation(op="upsert"))


def test_malformed_client_request_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Mutation.model_validate(_mutation(client_request_id="not-a-uuid"))


def test_non_v7_uuid_accepted() -> None:
    """D7 : le serveur accepte tout UUID bien formé (un v4 passe) — la v7 reste
    une recommandation client, jamais une contrainte serveur."""
    m = Mutation.model_validate(_mutation(client_request_id=str(uuid.uuid4())))
    assert m.client_request_id.version == 4


def test_table_length_bounded() -> None:
    with pytest.raises(ValidationError):
        Mutation.model_validate(_mutation(table="t" * (_MAX_TABLE_NAME + 1)))
    # La borne exacte passe.
    assert Mutation.model_validate(_mutation(table="t" * _MAX_TABLE_NAME)).table


def test_extra_field_on_mutation_rejected() -> None:
    with pytest.raises(ValidationError):
        Mutation.model_validate(_mutation(unexpected="x"))


def test_arbitrary_keys_inside_payload_accepted() -> None:
    """`extra="forbid"` borne l'ENVELOPPE, pas l'intérieur du `payload` opaque (D8)."""
    m = Mutation.model_validate(_mutation(payload={"any_key": {"nested": [1, 2, 3]}}))
    assert m.payload == {"any_key": {"nested": [1, 2, 3]}}


# --- validation : BatchUpload ----------------------------------------------


def test_empty_batch_is_valid() -> None:
    """Batch vide = no-op valide (D9) — jamais un chemin d'erreur pour le client."""
    assert BatchUpload(mutations=[]).mutations == []


def test_batch_cardinality_bounded() -> None:
    too_many = [_mutation() for _ in range(_MAX_MUTATIONS + 1)]
    with pytest.raises(ValidationError):
        BatchUpload.model_validate({"mutations": too_many})


def test_extra_field_on_batch_rejected() -> None:
    with pytest.raises(ValidationError):
        BatchUpload.model_validate({"mutations": [], "extra": 1})


# --- validation : WriteError / WriteResult ---------------------------------


def test_write_error_well_formed() -> None:
    err = WriteError(code="validation_error", message="…")
    assert err.code == "validation_error"


def test_extra_field_on_write_error_rejected() -> None:
    with pytest.raises(ValidationError):
        WriteError.model_validate({"code": "x", "message": "y", "detail": "leak"})


def test_write_result_minimal_success() -> None:
    res = WriteResult(client_request_id=uuid.uuid4(), success=True)
    assert res.error is None
    assert res.server_values is None


def test_extra_field_on_write_result_rejected() -> None:
    with pytest.raises(ValidationError):
        WriteResult.model_validate(
            {"client_request_id": str(uuid.uuid4()), "success": True, "rogue": 1}
        )
