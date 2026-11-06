import pytest
from amplifier_core import ModelInfo
from amplifier_core.message_models import ChatRequest, Message
from amplifier_module_provider_mock import MockProvider


@pytest.mark.asyncio
async def test_simulated_catalog_and_exact_canned_inference():
    provider = MockProvider({"model_filters": {"include": []}, "responses": ["fixture result"]})
    assert provider.get_model_list_info()["source"] == "simulated"
    assert await provider.list_models() == []
    all_models = await provider.list_models(filters={})
    assert len(all_models) == 1 and isinstance(all_models[0], ModelInfo)
    assert all_models[0].id == "mock-model"
    assert [m.id for m in await provider.list_models(filters={"include": ["MOCK*"]})] == ["mock-model"]
    assert await provider.list_models(filters={"exclude": ["MOCK*"]}) == []
    response = await provider.complete(ChatRequest(messages=[Message(role="user", content="hello")], model="mock-model"))
    assert response.content[0].text == "fixture result"


@pytest.mark.asyncio
async def test_snapshot_defaults_and_fresh_metadata():
    config = {"model_filters": {"include": ["mock*"]}}
    provider = MockProvider(config)
    config["model_filters"]["include"].clear()
    info = provider.get_model_list_info()
    info["default_filters"]["include"].clear()
    info["filters_schema"]["properties"].clear()
    assert len(await provider.list_models(filters=None)) == 1
    assert provider.get_model_list_info()["filters_schema"]["properties"]
    assert await provider.list_models(filters={"include": []}) == []


@pytest.mark.parametrize("invalid", [None, [], {"include": "*"}, {"hide_dated": 1}])
def test_invalid_config(invalid):
    with pytest.raises((TypeError, ValueError)):
        MockProvider({"model_filters": invalid})
