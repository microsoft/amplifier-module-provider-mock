"""
Mock provider module for testing.
Returns pre-configured responses without calling real APIs.
"""

import logging
from typing import Any
from typing import Optional

from amplifier_core import ModuleCoordinator
from amplifier_core import ProviderResponse
from amplifier_core import ToolCall

logger = logging.getLogger(__name__)


async def mount(coordinator: ModuleCoordinator, config: dict[str, Any] | None = None):
    """Mount the mock provider."""
    config = config or {}
    provider = MockProvider(config)
    await coordinator.mount("providers", provider, name="mock")
    logger.info("Mounted MockProvider")
    return


class MockProvider:
    """Mock provider for testing without API calls."""

    name = "mock"

    def __init__(self, config: dict[str, Any]):
        self.responses = config.get(
            "responses",
            ["I'll help you with that task.", "Task completed successfully.", "Here's the result of your request."],
        )
        self.call_count = 0

    async def complete(self, messages: list[dict[str, Any]], **kwargs) -> ProviderResponse:
        """Generate a mock completion."""
        self.call_count += 1

        # Check if we should return a tool call
        last_message = messages[-1] if messages else {}
        content = last_message.get("content", "")

        # Simple pattern matching for tool calls
        if "read" in content.lower():
            return ProviderResponse(
                content="", raw=None, tool_calls=[ToolCall(tool="read", arguments={"path": "test.txt"})]
            )

        # Return a regular response
        response_text = self.responses[self.call_count % len(self.responses)]
        return ProviderResponse(content=response_text, raw=None, usage={"input": 10, "output": 20})

    def parse_tool_calls(self, response: ProviderResponse) -> list[ToolCall]:
        """Parse tool calls from response."""
        return response.tool_calls or []
