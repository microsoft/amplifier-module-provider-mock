"""Copied provider-local selector conformance; no service credentials or I/O."""
import pytest
from amplifier_module_provider_mock._model_listing import ModelFilters


@pytest.mark.parametrize("filters,expected", [
    ({}, ["Custom:Q4", "GPT-6", "gpt-6-2026-01-01", "older"]),
    ({"include": []}, []),
    ({"include": ["gPt*"], "exclude": ["*2026*"]}, ["GPT-6"]),
    ({"include": ["*"], "exclude": ["*"]}, []),
    ({"include": ["CUSTOM:*"]}, ["Custom:Q4"]),
])
def test_vectors(filters, expected):
    assert ModelFilters.parse(filters).select(["GPT-6", "older", "gpt-6-2026-01-01", "Custom:Q4"]) == expected


def test_snapshots_and_caller_mutation():
    raw = {"include": ["gpt*"]}
    policy = ModelFilters.parse(raw)
    raw["include"].clear()
    info = policy.as_dict()
    info["include"].clear()
    assert policy.select(["gpt-6"]) == ["gpt-6"]
    assert ModelFilters.parse({"hide_dated": True}).select(["gpt-6", "gpt-6-2026-01-01", "other-2026-01-01"]) == ["gpt-6", "other-2026-01-01"]


@pytest.mark.parametrize("invalid", [None, [], "*", {"include":"*"}, {"include":[None]}, {"exclude":[""]}, {"include":[" "]}, {"hide_dated":1}, {"unknown":True}])
def test_invalid(invalid):
    with pytest.raises((TypeError, ValueError)):
        ModelFilters.parse(invalid)
