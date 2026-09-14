import pytest
from pydantic import ValidationError

from app.model_catalog import CATALOG
from app.schemas import RunRequest

# This app is deployed publicly with a real, billed SI API key behind an
# unauthenticated POST /api/jobs — these validators are the only thing
# standing between a random caller and unbounded spend, so they need
# regression coverage same as any other correctness bug in this repo.

A_MODEL, B_MODEL = list(CATALOG.keys())[:2]


def test_accepts_valid_request():
    req = RunRequest(model_a=A_MODEL, model_b=B_MODEL, concurrency=8, limit=10)
    assert req.model_a == A_MODEL


def test_rejects_model_not_in_catalog():
    with pytest.raises(ValidationError):
        RunRequest(model_a="not-a-real-model", model_b=B_MODEL)


def test_rejects_concurrency_above_bound():
    with pytest.raises(ValidationError):
        RunRequest(model_a=A_MODEL, model_b=B_MODEL, concurrency=10_000)


def test_rejects_concurrency_below_bound():
    with pytest.raises(ValidationError):
        RunRequest(model_a=A_MODEL, model_b=B_MODEL, concurrency=0)


def test_rejects_limit_above_corpus_size():
    with pytest.raises(ValidationError):
        RunRequest(model_a=A_MODEL, model_b=B_MODEL, limit=100_000)


def test_allows_unset_limit_for_full_corpus_run():
    req = RunRequest(model_a=A_MODEL, model_b=B_MODEL)
    assert req.limit is None
