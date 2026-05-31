"""
Streaming conformance tests for the mock provider.

Asserts the exact event sequences required by the provider streaming contract.
See: docs/provider-streaming-contract.md (in the streaming-text repo)
"""

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test-local fakes — no Rust coordinator needed for event-capture unit tests
# ---------------------------------------------------------------------------


class _FakeHooks:
    """Records every emit() call so tests can assert exact event sequences."""

    def __init__(self):
        self.events: list[dict] = []

    async def emit(self, name: str, payload: dict) -> None:
        self.events.append({"name": name, "payload": payload})


class _FakeCoordinator:
    """Minimal coordinator that satisfies the emit guard in MockProvider."""

    def __init__(self):
        self.hooks = _FakeHooks()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(text: str, metadata: dict | None = None):
    """Build a minimal ChatRequest with a single user message."""
    from amplifier_core.message_models import ChatRequest, Message

    return ChatRequest(
        messages=[Message(role="user", content=text)],
        metadata=metadata,
    )


def _events_named(events: list[dict], name: str) -> list[dict]:
    return [e for e in events if e["name"] == name]


def _stream_events(events: list[dict]) -> list[dict]:
    return [e for e in events if "stream" in e["name"]]


# ---------------------------------------------------------------------------
# 1. Plain text streaming — exact sequence
# ---------------------------------------------------------------------------


async def test_plain_text_emits_correct_event_sequence():
    """block_start -> N block_deltas -> block_end, plus llm:request and llm:response."""
    from amplifier_module_provider_mock import MockProvider

    words = ["Hello", "world", "foo"]
    text = " ".join(words)  # "Hello world foo"

    coordinator = _FakeCoordinator()
    provider = MockProvider(
        {"responses": [text], "use_streaming": True},
        coordinator,  # type: ignore[arg-type]
    )
    response = await provider.complete(_make_request("hi"))

    events = coordinator.hooks.events
    names = [e["name"] for e in events]

    # Top-level ordering: llm:request first, llm:response last
    assert names[0] == "llm:request", f"First event should be llm:request, got {names}"
    assert names[-1] == "llm:response", (
        f"Last event should be llm:response, got {names}"
    )

    # All five stream-related events present
    assert "llm:stream_block_start" in names
    assert "llm:stream_block_delta" in names
    assert "llm:stream_block_end" in names

    # Ordering: start < first delta < end
    start_idx = names.index("llm:stream_block_start")
    first_delta_idx = names.index("llm:stream_block_delta")
    end_idx = next(i for i, n in enumerate(names) if n == "llm:stream_block_end")
    assert start_idx < first_delta_idx < end_idx

    # All stream events share exactly one request_id
    stream_evts = _stream_events(events)
    request_ids = {e["payload"]["request_id"] for e in stream_evts}
    assert len(request_ids) == 1, f"Expected 1 request_id, got {request_ids}"
    assert list(request_ids)[0]  # non-empty

    # block_start shape
    start = _events_named(events, "llm:stream_block_start")[0]
    assert start["payload"]["block_index"] == 0
    assert start["payload"]["block_type"] == "text"

    # Deltas: sequence 0..N-1, correct word+space text, correct block_index
    deltas = _events_named(events, "llm:stream_block_delta")
    assert len(deltas) == len(words), f"Expected {len(words)} deltas, got {len(deltas)}"
    for i, delta in enumerate(deltas):
        p = delta["payload"]
        assert p["block_index"] == 0
        assert p["sequence"] == i, f"Sequence {i}: expected {i}, got {p['sequence']}"
        assert p["text"] == words[i] + " ", (
            f"Expected {words[i] + ' '!r}, got {p['text']!r}"
        )
        assert p["text"]  # non-empty guard
        assert p["block_type"] == "text", (
            f"Plain-text delta must carry block_type='text', got {p.get('block_type')!r}"
        )

    # block_end shape
    end = _events_named(events, "llm:stream_block_end")[0]
    assert end["payload"]["block_index"] == 0
    assert end["payload"]["block_type"] == "text"

    # llm:response payload
    resp_evt = _events_named(events, "llm:response")[0]
    rp = resp_evt["payload"]
    assert rp["provider"] == "mock"
    assert rp["status"] == "ok"
    assert "usage" in rp
    assert rp["usage"]["input_tokens"] >= 0

    # ChatResponse is valid
    assert response is not None
    assert response.content


# ---------------------------------------------------------------------------
# 2. Thinking dict — two-block sequence
# ---------------------------------------------------------------------------


async def test_thinking_dict_emits_thinking_block_then_text_block():
    """
    A {"thinking": "...", "text": "..."} entry must emit (per contract):
      block_start(thinking, index=0) ->
      N block_deltas(block_type="thinking", block_index=0) ->
      block_end(thinking, index=0) ->
      block_start(text, index=1) ->
      M block_deltas(block_type="text", block_index=1) ->
      block_end(text, index=1)

    Contract: ONE delta event (llm:stream_block_delta) for ALL content;
    block_type on every delta distinguishes thinking from text.
    llm:stream_thinking_delta is REMOVED from the contract.
    """
    from amplifier_module_provider_mock import MockProvider

    thinking_words = ["Let", "me", "think"]
    text_words = ["Here", "is", "the", "answer"]
    entry = {
        "thinking": " ".join(thinking_words),
        "text": " ".join(text_words),
    }

    coordinator = _FakeCoordinator()
    provider = MockProvider(
        {"responses": [entry], "use_streaming": True},
        coordinator,  # type: ignore[arg-type]
    )
    await provider.complete(_make_request("explain"))

    events = coordinator.hooks.events
    names = [e["name"] for e in events]

    # Contract: llm:stream_thinking_delta must NOT appear; only block_delta
    assert "llm:stream_thinking_delta" not in names, (
        "llm:stream_thinking_delta is removed from the contract; "
        "use llm:stream_block_delta with block_type='thinking'"
    )
    assert "llm:stream_block_delta" in names

    # All stream events share one request_id
    stream_evts = _stream_events(events)
    request_ids = {e["payload"]["request_id"] for e in stream_evts}
    assert len(request_ids) == 1

    # Two block_starts: thinking (index 0) then text (index 1)
    starts = _events_named(events, "llm:stream_block_start")
    assert len(starts) == 2
    assert starts[0]["payload"]["block_index"] == 0
    assert starts[0]["payload"]["block_type"] == "thinking"
    assert starts[1]["payload"]["block_index"] == 1
    assert starts[1]["payload"]["block_type"] == "text"

    # Thinking deltas: llm:stream_block_delta with block_type="thinking"
    thinking_deltas = [
        e for e in _events_named(events, "llm:stream_block_delta")
        if e["payload"].get("block_type") == "thinking"
    ]
    assert len(thinking_deltas) == len(thinking_words), (
        f"Expected {len(thinking_words)} thinking deltas, got {len(thinking_deltas)}"
    )
    for i, delta in enumerate(thinking_deltas):
        p = delta["payload"]
        assert p["block_index"] == 0
        assert p["block_type"] == "thinking"
        assert p["sequence"] == i
        assert p["text"] == thinking_words[i] + " "

    # Text deltas: llm:stream_block_delta with block_type="text"
    text_deltas = [
        e for e in _events_named(events, "llm:stream_block_delta")
        if e["payload"].get("block_type") == "text"
    ]
    assert len(text_deltas) == len(text_words), (
        f"Expected {len(text_words)} text deltas, got {len(text_deltas)}"
    )
    for i, delta in enumerate(text_deltas):
        p = delta["payload"]
        assert p["block_index"] == 1
        assert p["block_type"] == "text"
        assert p["sequence"] == i
        assert p["text"] == text_words[i] + " "

    # Two block_ends: thinking (index 0) then text (index 1)
    ends = _events_named(events, "llm:stream_block_end")
    assert len(ends) == 2
    assert ends[0]["payload"]["block_index"] == 0
    assert ends[0]["payload"]["block_type"] == "thinking"
    assert ends[1]["payload"]["block_index"] == 1
    assert ends[1]["payload"]["block_type"] == "text"

    # Thinking block_end comes before text block_start
    thinking_end_pos = next(
        i for i, e in enumerate(events) if e["name"] == "llm:stream_block_end"
    )
    text_start_pos = next(
        i
        for i, e in enumerate(events)
        if e["name"] == "llm:stream_block_start" and e["payload"]["block_index"] == 1
    )
    assert thinking_end_pos < text_start_pos


# ---------------------------------------------------------------------------
# 3. metadata stream=False — no stream events
# ---------------------------------------------------------------------------


async def test_metadata_stream_false_suppresses_stream_events():
    """request.metadata={"stream": False} must emit NO llm:stream_* events."""
    from amplifier_module_provider_mock import MockProvider

    coordinator = _FakeCoordinator()
    provider = MockProvider(
        {"responses": ["Hello world"], "use_streaming": True},
        coordinator,  # type: ignore[arg-type]
    )
    response = await provider.complete(_make_request("hi", metadata={"stream": False}))

    events = coordinator.hooks.events
    names = [e["name"] for e in events]

    stream_names = [n for n in names if "stream" in n]
    assert stream_names == [], f"Expected no stream events, got: {stream_names}"

    # llm:request and llm:response still emitted
    assert "llm:request" in names
    assert "llm:response" in names

    # Still returns a valid ChatResponse
    assert response is not None
    assert response.content


# ---------------------------------------------------------------------------
# 4. config use_streaming=False — no stream events
# ---------------------------------------------------------------------------


async def test_config_use_streaming_false_suppresses_stream_events():
    """Config use_streaming=False is the class-level default suppressor."""
    from amplifier_module_provider_mock import MockProvider

    coordinator = _FakeCoordinator()
    provider = MockProvider(
        {"responses": ["Hello world"], "use_streaming": False},
        coordinator,  # type: ignore[arg-type]
    )
    response = await provider.complete(_make_request("hi"))

    events = coordinator.hooks.events
    names = [e["name"] for e in events]

    stream_names = [n for n in names if "stream" in n]
    assert stream_names == []
    assert "llm:request" in names
    assert "llm:response" in names
    assert response is not None


# ---------------------------------------------------------------------------
# 5. Per-call override is local — does NOT mutate self.use_streaming
# ---------------------------------------------------------------------------


async def test_stream_false_override_does_not_mutate_class_state():
    """stream=False override must be local; subsequent calls still stream."""
    from amplifier_module_provider_mock import MockProvider

    text = "one two"
    coordinator = _FakeCoordinator()
    provider = MockProvider(
        {"responses": [text], "use_streaming": True},
        coordinator,  # type: ignore[arg-type]
    )

    # Call 1: override to non-streaming
    await provider.complete(_make_request("hi", metadata={"stream": False}))
    events_after_call1 = list(coordinator.hooks.events)
    stream_names_1 = [e["name"] for e in events_after_call1 if "stream" in e["name"]]
    assert stream_names_1 == [], "call 1 (overridden) should have no stream events"

    # Call 2: no override — streaming should be restored
    coordinator.hooks.events.clear()
    await provider.complete(_make_request("hi"))
    events_after_call2 = coordinator.hooks.events
    stream_names_2 = [e["name"] for e in events_after_call2 if "stream" in e["name"]]
    assert stream_names_2, "call 2 (no override) should have stream events"
    assert provider.use_streaming is True, "use_streaming must not have been mutated"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 6. Tool-call response — no stream events
# ---------------------------------------------------------------------------


async def test_tool_call_response_emits_no_stream_events():
    """Tool call responses must not emit llm:stream_* events per contract."""
    from amplifier_module_provider_mock import MockProvider

    coordinator = _FakeCoordinator()
    provider = MockProvider({"responses": ["OK"]}, coordinator)  # type: ignore[arg-type]

    # "read" keyword triggers the mock tool-call path
    response = await provider.complete(_make_request("please read the file"))

    events = coordinator.hooks.events
    names = [e["name"] for e in events]

    stream_names = [n for n in names if "stream" in n]
    assert stream_names == [], f"Tool calls must not stream; got: {stream_names}"
    assert "llm:request" in names
    assert "llm:response" in names
    assert response.tool_calls, "Expected tool_calls in response"


# ---------------------------------------------------------------------------
# 7. llm:request always emitted — before streaming starts
# ---------------------------------------------------------------------------


async def test_llm_request_is_first_event():
    """llm:request must be the very first event emitted in all paths."""
    from amplifier_module_provider_mock import MockProvider

    coordinator = _FakeCoordinator()
    provider = MockProvider({"responses": ["alpha beta"]}, coordinator)  # type: ignore[arg-type]
    await provider.complete(_make_request("hi"))

    names = [e["name"] for e in coordinator.hooks.events]
    assert names[0] == "llm:request"


# ---------------------------------------------------------------------------
# 8. No coordinator — no crash
# ---------------------------------------------------------------------------


async def test_no_coordinator_returns_valid_response():
    """MockProvider without a coordinator must still return a valid ChatResponse."""
    from amplifier_module_provider_mock import MockProvider

    provider = MockProvider({"responses": ["fine"]})
    response = await provider.complete(_make_request("hi"))
    assert response is not None
    assert response.content


# ---------------------------------------------------------------------------
# 9. capabilities includes "streaming"
# ---------------------------------------------------------------------------


def test_get_info_capabilities_includes_streaming():
    """get_info() must report 'streaming' in capabilities (contract item 8)."""
    from amplifier_module_provider_mock import MockProvider

    provider = MockProvider({})
    info = provider.get_info()
    assert "streaming" in info.capabilities, (
        f"'streaming' not found in capabilities: {info.capabilities}"
    )


# ---------------------------------------------------------------------------
# 10. request_id is a valid UUID4 string
# ---------------------------------------------------------------------------


async def test_request_id_is_uuid4_string():
    """request_id on all stream events must be a valid UUID4 string."""
    import re

    UUID4_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )

    from amplifier_module_provider_mock import MockProvider

    coordinator = _FakeCoordinator()
    provider = MockProvider({"responses": ["alpha beta gamma"]}, coordinator)  # type: ignore[arg-type]
    await provider.complete(_make_request("hi"))

    stream_evts = _stream_events(coordinator.hooks.events)
    assert stream_evts, "Expected stream events to inspect request_id"
    for evt in stream_evts:
        rid = evt["payload"].get("request_id", "")
        assert UUID4_RE.match(rid), f"request_id {rid!r} is not a valid UUID4"
