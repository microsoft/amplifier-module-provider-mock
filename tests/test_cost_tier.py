"""Tests for cost tier metadata in Mock provider.

Validates:
1. list_models() adds cost_per_input/output_token = 0.0
2. list_models() adds metadata={"cost_tier": "free"}
"""

import pytest

from amplifier_module_provider_mock import MockProvider


class TestMockCostTier:
    """Verify mock model gets free cost tier."""

    @pytest.fixture
    def provider(self):
        return MockProvider(config={})

    @pytest.mark.asyncio
    async def test_mock_model_has_free_cost_tier(self, provider):
        models = await provider.list_models()

        assert len(models) == 1
        model = models[0]
        assert model.metadata == {"cost_tier": "free"}

    @pytest.mark.asyncio
    async def test_mock_model_has_zero_cost(self, provider):
        models = await provider.list_models()

        model = models[0]
        assert model.cost_per_input_token == 0.0
        assert model.cost_per_output_token == 0.0

    @pytest.mark.asyncio
    async def test_mock_model_preserves_existing_fields(self, provider):
        """New fields should not break existing capabilities and defaults."""
        models = await provider.list_models()

        model = models[0]
        assert model.id == "mock-model"
        assert "tools" in model.capabilities
        assert model.context_window == 100000
