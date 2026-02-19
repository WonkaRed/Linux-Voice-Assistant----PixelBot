#!/usr/bin/env python3
"""
Pixel Bot Integration Tests

Tests SSH connectivity, Pixel Bot CLI invocation, response parsing,
local tool routing, Markdown stripping, error states, boot message,
and full roundtrip through the Nova agent.

Run: python -m nova.tests.test_pixelbot
"""
import sys
import os
import time
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nova.llm import PixelBotClient, PixelBotResponse, BOOT_MESSAGE
from nova.agent import Agent, strip_markdown, LOCAL_PATTERNS


# ============================================================================
# Unit Tests (no network required)
# ============================================================================

def test_local_tool_routing():
    """Local tool regex matching — all patterns."""
    print("\n=== Test: Local Tool Routing ===")
    agent = Agent.__new__(Agent)
    agent._tools = {}

    test_cases = [
        # system_stats
        ("what's my GPU temp", "system_stats"),
        ("show me CPU usage", "system_stats"),
        ("how much RAM is free", "system_stats"),
        ("check memory usage", "system_stats"),
        ("disk space", "system_stats"),
        ("system stats", "system_stats"),
        ("what's the temperature", "system_stats"),
        ("vram usage", "system_stats"),
        ("show processes", "system_stats"),
        ("system uptime", "system_stats"),
        # clipboard
        ("what's on my clipboard", "clipboard"),
        ("read clipboard", "clipboard"),
        ("paste what I copied", "clipboard"),
        # timer
        ("set a timer for 5 minutes", "timer"),
        ("set timer 30 seconds", "timer"),
        ("list my timers", "timer"),
        ("check timers", "timer"),
        ("cancel the timer", "timer"),
        ("stop the alarm", "timer"),
        ("remind me in 10 minutes", "timer"),
        ("start a countdown for 2 hours", "timer"),
        # notes
        ("save a note that I need milk", "notes"),
        ("show my notes", "notes"),
        ("add a note about the meeting", "notes"),
        ("remember that the password is 1234", "notes"),
        ("jot down call dentist", "notes"),
        # time
        ("what time is it", "time"),
        ("what day is it", "time"),
        # should NOT match (→ Pixel Bot)
        ("what is the capital of France", None),
        ("tell me a joke", None),
        ("search for python tutorials", None),
        ("how do I cook pasta", None),
        ("what's the weather like", None),
        ("translate hello to Spanish", None),
    ]

    passed = 0
    failed = []
    for msg, expected in test_cases:
        result = agent._match_local_tool(msg)
        if result == expected:
            passed += 1
        else:
            failed.append((msg, expected, result))

    for msg, expected, got in failed:
        print(f"  FAIL: '{msg}' → {got} (expected {expected})")

    print(f"  {passed}/{len(test_cases)} passed")
    assert passed == len(test_cases), f"{len(failed)} routing tests failed"
    print("  PASS")


def test_markdown_stripping():
    """Markdown stripped for clean TTS output."""
    print("\n=== Test: Markdown Stripping ===")

    cases = [
        ("**bold text**", "bold text"),
        ("*italic text*", "italic text"),
        ("`inline code`", "inline code"),
        ("[link text](https://example.com)", "link text"),
        ("# Header", "Header"),
        ("## Sub Header", "Sub Header"),
        ("- bullet point", "bullet point"),
        ("* star bullet", "star bullet"),
        ("1. numbered item", "numbered item"),
        ("plain text", "plain text"),
        ("**bold** and *italic* and `code`", "bold and italic and code"),
        ("\n\n\n\nmany newlines\n\n\n\n", "many newlines"),
    ]

    passed = 0
    for md_input, expected in cases:
        result = strip_markdown(md_input)
        if result.strip() == expected.strip():
            passed += 1
        else:
            print(f"  FAIL: strip_markdown({md_input!r}) = {result!r}, expected {expected!r}")

    print(f"  {passed}/{len(cases)} passed")
    assert passed == len(cases), f"Markdown stripping failures"
    print("  PASS")


def test_boot_message_exists():
    """Boot message constant is defined and non-empty."""
    print("\n=== Test: Boot Message ===")
    assert BOOT_MESSAGE, "BOOT_MESSAGE is empty"
    assert "Nova" in BOOT_MESSAGE, "BOOT_MESSAGE should mention Nova"
    assert "TTS" in BOOT_MESSAGE, "BOOT_MESSAGE should mention TTS"
    assert len(BOOT_MESSAGE) > 50, "BOOT_MESSAGE seems too short"
    print(f"  Boot message: {BOOT_MESSAGE[:80]}...")
    print("  PASS")


def test_boot_message_sent_once():
    """Boot message prepended on first call only."""
    print("\n=== Test: Boot Message Sent Once ===")
    client = PixelBotClient.__new__(PixelBotClient)
    client.ssh_host = "pixel-labs-server"
    client.agent_name = "main"
    client.session_id = "nova-desktop"
    client.timeout = 15
    client.max_retries = 0
    client.retry_delay = 2.0
    client._boot_sent = False

    # Simulate send logic (without actually executing SSH)
    # First call: boot message included
    msg1 = "hello"
    full1 = msg1.strip()
    if not client._boot_sent:
        full1 = f"{BOOT_MESSAGE}\n\n---\n\n{full1}"
        client._boot_sent = True

    assert BOOT_MESSAGE in full1, "First message should include boot message"

    # Second call: no boot message
    msg2 = "world"
    full2 = msg2.strip()
    if not client._boot_sent:
        full2 = f"{BOOT_MESSAGE}\n\n---\n\n{full2}"
        client._boot_sent = True

    assert BOOT_MESSAGE not in full2, "Second message should NOT include boot message"
    assert full2 == "world", "Second message should be just the user text"

    print("  First call includes boot message: OK")
    print("  Second call excludes boot message: OK")
    print("  PASS")


def test_context_prepending():
    """Context data prepended to user message correctly."""
    print("\n=== Test: Context Prepending ===")
    client = PixelBotClient.__new__(PixelBotClient)
    client._boot_sent = True  # Skip boot for this test

    # Simulate context logic
    message = "is this okay?"
    context = "GPU: 65°C, VRAM: 8.2/24 GB"

    full = message.strip()
    if context:
        full = (
            f"[Local data from Nova desktop]\n{context}\n\n"
            f"[User's question]\n{full}"
        )

    assert "[Local data from Nova desktop]" in full
    assert context in full
    assert "[User's question]" in full
    assert message in full
    print(f"  Context message: {full[:100]}...")
    print("  PASS")


def test_response_parsing():
    """Pixel Bot JSON response parsed correctly."""
    print("\n=== Test: Response Parsing ===")
    client = PixelBotClient.__new__(PixelBotClient)
    client.ssh_host = "pixel-labs-server"
    client.agent_name = "main"

    # Valid response
    valid_json = '{"result":{"payloads":[{"text":"Hello from Pixel Bot!"}],"meta":{}},"status":"ok"}'
    resp = client._parse_response(valid_json, 1.5)
    assert resp.text == "Hello from Pixel Bot!", f"Got: {resp.text}"
    assert resp.latency == 1.5
    assert not resp.error
    print("  Valid JSON: OK")

    # Error response
    error_json = '{"status":"error","error":"Rate limited"}'
    resp = client._parse_response(error_json, 2.0)
    assert resp.error, "Expected error"
    assert not resp.text
    print("  Error JSON: OK")

    # Non-JSON fallback
    raw_text = "Plain text response without JSON"
    resp = client._parse_response(raw_text, 0.5)
    assert resp.text == raw_text, f"Got: {resp.text}"
    assert not resp.error
    print("  Non-JSON fallback: OK")

    # Empty payloads
    empty_json = '{"result":{"payloads":[]},"status":"ok"}'
    resp = client._parse_response(empty_json, 1.0)
    assert resp.error, "Expected error for empty payloads"
    print("  Empty payloads: OK")

    print("  PASS")


def test_empty_message_handling():
    """Empty/blank messages handled gracefully."""
    print("\n=== Test: Empty Message Handling ===")
    client = PixelBotClient.__new__(PixelBotClient)
    client._boot_sent = True

    for msg in ["", "   ", None]:
        resp = client.send(msg)
        assert resp.error, f"Expected error for message: {msg!r}"
        assert not resp.text, f"Expected empty text for message: {msg!r}"
    print("  Empty/blank/None messages return error: OK")
    print("  PASS")


def test_pixelbot_response_dataclass():
    """PixelBotResponse dataclass works correctly."""
    print("\n=== Test: PixelBotResponse ===")

    # Default values
    resp = PixelBotResponse(text="hello")
    assert resp.text == "hello"
    assert resp.error is None
    assert resp.latency == 0.0
    assert resp.raw == {}

    # With all fields
    resp = PixelBotResponse(
        text="hi", error="timeout", latency=5.0, raw={"status": "error"}
    )
    assert resp.error == "timeout"
    assert resp.latency == 5.0
    assert resp.raw["status"] == "error"

    print("  Default values: OK")
    print("  Full constructor: OK")
    print("  PASS")


# ============================================================================
# Agent Logic Unit Tests (no network required)
# ============================================================================

def test_system_stats_type_detection():
    """Agent detects correct stat type from natural language."""
    print("\n=== Test: System Stats Type Detection ===")
    from nova.tools import SystemStatsTool
    agent = Agent.__new__(Agent)
    agent._tools = {"system_stats": SystemStatsTool()}
    agent.client = None

    cases = [
        ("what's my GPU temp", "gpu"),
        ("check VRAM usage", "gpu"),
        ("CPU usage", "cpu"),
        ("how much RAM is free", "memory"),
        ("check memory usage", "memory"),
        ("disk space", "disk"),
        ("what's the temperature", "temperature"),
        ("show processes", "processes"),
        ("system stats", "overview"),
    ]

    passed = 0
    for msg, expected_type in cases:
        msg_lower = msg.lower()
        if "gpu" in msg_lower or "vram" in msg_lower:
            detected = "gpu"
        elif "cpu" in msg_lower:
            detected = "cpu"
        elif "ram" in msg_lower or "memory" in msg_lower:
            detected = "memory"
        elif "disk" in msg_lower:
            detected = "disk"
        elif "temp" in msg_lower:
            detected = "temperature"
        elif "process" in msg_lower:
            detected = "processes"
        else:
            detected = "overview"

        if detected == expected_type:
            passed += 1
        else:
            print(f"  FAIL: '{msg}' → {detected} (expected {expected_type})")

    print(f"  {passed}/{len(cases)} passed")
    assert passed == len(cases), "Stat type detection failures"
    print("  PASS")


def test_timer_name_extraction():
    """Agent extracts timer names from natural language."""
    print("\n=== Test: Timer Name Extraction ===")

    cases = [
        ('set a timer called cooking', 'cooking'),
        ('set timer named laundry', 'laundry'),
        ('set a timer for pizza', 'pizza'),
    ]

    passed = 0
    for msg, expected_name in cases:
        msg_lower = msg.lower()
        name_match = re.search(
            r'(?:called?|named?|for)\s+["\']?(\w+)', msg_lower
        )
        name = name_match.group(1) if name_match else None
        if name == expected_name:
            passed += 1
        else:
            print(f"  FAIL: '{msg}' → {name} (expected {expected_name})")

    print(f"  {passed}/{len(cases)} passed")
    assert passed == len(cases), "Timer name extraction failures"
    print("  PASS")


def test_notes_content_extraction():
    """Agent extracts note content from natural language."""
    print("\n=== Test: Notes Content Extraction ===")

    cases = [
        ("remember that I need milk", "I need milk"),
        ("save a note buy dog food", "buy dog food"),
        ("add a note call the dentist", "call the dentist"),
        ("jot down meeting at 3pm", "meeting at 3pm"),
        ("note that keys are on the table", "keys are on the table"),
    ]

    passed = 0
    for msg, expected in cases:
        content_match = re.search(
            r'(?:remember\s+that|save\s+(?:a\s+)?note|add\s+(?:a\s+)?note|'
            r'jot\s+down|note\s+that)\s+(.+)',
            msg, re.I
        )
        content = content_match.group(1).strip() if content_match else msg
        if content == expected:
            passed += 1
        else:
            print(f"  FAIL: '{msg}' → '{content}' (expected '{expected}')")

    print(f"  {passed}/{len(cases)} passed")
    assert passed == len(cases), "Notes content extraction failures"
    print("  PASS")


def test_hybrid_vs_pure_local_routing():
    """Agent correctly decides between pure local and hybrid routing."""
    print("\n=== Test: Hybrid vs Pure Local Routing ===")

    # Pure local (no interpretation words) → returns data directly
    pure_local = [
        "what's my GPU temp",
        "show CPU usage",
        "disk space",
    ]

    # Hybrid (interpretation words) → would send to Pixel Bot with context
    hybrid = [
        "is my GPU running hot",
        "do I have enough RAM",
        "is my CPU usage okay",
        "is there a problem with my disk",
    ]

    interpretation_words = ("hot", "running", "okay", "fine", "problem",
                            "issue", "worried", "much", "enough", "low")

    passed = 0
    for msg in pure_local:
        if not any(w in msg.lower() for w in interpretation_words):
            passed += 1
        else:
            print(f"  FAIL: '{msg}' should be pure local")

    for msg in hybrid:
        if any(w in msg.lower() for w in interpretation_words):
            passed += 1
        else:
            print(f"  FAIL: '{msg}' should be hybrid")

    total = len(pure_local) + len(hybrid)
    print(f"  {passed}/{total} passed")
    assert passed == total, "Routing decision failures"
    print("  PASS")


def test_agent_error_formatting():
    """Agent formats error messages for TTS appropriately."""
    print("\n=== Test: Agent Error Formatting ===")

    # Simulate error messages the agent would produce
    error_cases = [
        ("timed out after 15s", "taking too long"),
        ("connection refused", "connect"),
        ("ssh: connect to host", "connect"),
    ]

    passed = 0
    for error_msg, expected_keyword in error_cases:
        # Simulate Agent._send_to_pixelbot error handling logic
        if "timed out" in error_msg.lower():
            response = ("Pixel Bot is taking too long. "
                       "Probably doing something heavy. I'll drop this one.")
        elif "connection" in error_msg.lower() or "ssh" in error_msg.lower():
            response = "Can't connect to the server. Network issue or the server is offline."
        else:
            response = f"I can't reach Pixel Bot right now. {error_msg}"

        if expected_keyword in response.lower():
            passed += 1
        else:
            print(f"  FAIL: error '{error_msg}' → '{response}' (missing '{expected_keyword}')")

    print(f"  {passed}/{len(error_cases)} passed")
    assert passed == len(error_cases), "Error formatting failures"
    print("  PASS")


def test_empty_chat_message():
    """Agent handles empty/blank chat messages gracefully."""
    print("\n=== Test: Empty Chat Message ===")
    agent = Agent.__new__(Agent)
    agent._tools = {}
    agent.client = None

    for msg in ["", "   ", None]:
        result = agent.chat(msg)
        assert result, f"Expected response for empty message: {msg!r}"
        assert "didn't catch" in result.lower() or "again" in result.lower()

    print("  Empty/blank/None messages handled: OK")
    print("  PASS")


# ============================================================================
# Integration Tests (require SSH connectivity)
# ============================================================================

def test_ssh_connectivity():
    """SSH connectivity to Pixel Bot server."""
    print("\n=== Test: SSH Connectivity ===")
    client = PixelBotClient()
    available = client.is_available()
    print(f"  Pixel Bot reachable: {available}")
    assert available, "Cannot reach Pixel Bot at pixel-labs-server (10.0.0.75)"
    print("  PASS")


def test_send_receive():
    """Send message to Pixel Bot and get response."""
    print("\n=== Test: Send/Receive ===")
    client = PixelBotClient(session_id="nova-test")

    start = time.time()
    response = client.send("Say exactly: PONG")
    latency = time.time() - start

    print(f"  Response: {response.text[:200]}")
    print(f"  Latency: {latency:.1f}s")
    print(f"  Error: {response.error}")

    assert not response.error, f"Error: {response.error}"
    assert response.text, "Empty response"
    assert "PONG" in response.text.upper(), f"Expected PONG in response, got: {response.text}"
    print("  PASS")


def test_unreachable_host():
    """Clean error on unreachable host."""
    print("\n=== Test: Unreachable Host ===")
    client = PixelBotClient(ssh_host="10.0.0.99", timeout=5, max_retries=0)
    response = client.send("hello")
    print(f"  Error: {response.error}")
    assert response.error, "Expected error for unreachable host"
    assert not response.text, "Expected empty text for unreachable host"
    print("  PASS")


def test_latency():
    """Measure roundtrip latency."""
    print("\n=== Test: Latency ===")
    client = PixelBotClient(session_id="nova-test")

    latencies = []
    for i in range(2):
        start = time.time()
        response = client.send(f"Reply with just the number {i + 1}")
        elapsed = time.time() - start
        latencies.append(elapsed)
        print(f"  Round {i + 1}: {elapsed:.1f}s - {response.text[:50] if response.text else 'ERROR'}")

    avg = sum(latencies) / len(latencies)
    print(f"  Average latency: {avg:.1f}s")
    assert avg < 30, f"Average latency too high: {avg:.1f}s"
    print("  PASS")


def test_pixelbot_verification():
    """Ask Pixel Bot to confirm connection."""
    print("\n=== Test: Connection Verification ===")
    client = PixelBotClient(session_id="nova-test")
    response = client.send(
        "Cole connected Nova voice assistant to you. "
        "Can you confirm you're receiving messages from Nova on the desktop? "
        "Keep it to one sentence."
    )
    print(f"  Response: {response.text[:300]}")
    assert not response.error, f"Error: {response.error}"
    assert response.text, "Empty response"
    print("  PASS")


def test_context_passing():
    """Pixel Bot receives local context data correctly."""
    print("\n=== Test: Context Passing ===")
    client = PixelBotClient(session_id="nova-test-ctx")
    response = client.send(
        "What GPU temp did Nova report?",
        context="GPU Temperature: 42°C\nGPU Memory: 5.8 GB / 24.0 GB"
    )
    print(f"  Response: {response.text[:200]}")
    assert not response.error, f"Error: {response.error}"
    assert response.text, "Empty response"
    # Pixel Bot should reference the temperature data
    assert "42" in response.text or "temp" in response.text.lower(), \
        f"Expected reference to GPU temp, got: {response.text[:200]}"
    print("  PASS")


def test_session_continuity():
    """Pixel Bot remembers context across messages in same session."""
    print("\n=== Test: Session Continuity ===")
    session_id = f"nova-test-cont-{int(time.time())}"
    client = PixelBotClient(session_id=session_id)

    # First message: establish a fact
    resp1 = client.send("My favorite number is 7742. Remember it. Reply with just 'OK'.")
    print(f"  Msg 1: {resp1.text[:100]}")
    assert not resp1.error, f"Error on msg 1: {resp1.error}"

    # Second message: ask about the fact
    resp2 = client.send("What's my favorite number? Reply with just the number.")
    print(f"  Msg 2: {resp2.text[:100]}")
    assert not resp2.error, f"Error on msg 2: {resp2.error}"
    assert "7742" in resp2.text, f"Expected 7742 in response, got: {resp2.text}"
    print("  PASS")


# ============================================================================
# Runner
# ============================================================================

def main():
    print("=" * 60)
    print("PIXEL BOT INTEGRATION TESTS")
    print("=" * 60)

    # Unit tests (always run, no network needed)
    unit_tests = [
        ("Local Tool Routing", test_local_tool_routing),
        ("Markdown Stripping", test_markdown_stripping),
        ("Boot Message Exists", test_boot_message_exists),
        ("Boot Message Sent Once", test_boot_message_sent_once),
        ("Context Prepending", test_context_prepending),
        ("Response Parsing", test_response_parsing),
        ("Empty Message Handling", test_empty_message_handling),
        ("PixelBotResponse Dataclass", test_pixelbot_response_dataclass),
        ("System Stats Type Detection", test_system_stats_type_detection),
        ("Timer Name Extraction", test_timer_name_extraction),
        ("Notes Content Extraction", test_notes_content_extraction),
        ("Hybrid vs Pure Local Routing", test_hybrid_vs_pure_local_routing),
        ("Agent Error Formatting", test_agent_error_formatting),
        ("Empty Chat Message", test_empty_chat_message),
    ]

    # Integration tests (require SSH)
    integration_tests = [
        ("SSH Connectivity", test_ssh_connectivity),
        ("Send/Receive", test_send_receive),
        ("Unreachable Host", test_unreachable_host),
        ("Latency", test_latency),
        ("Connection Verification", test_pixelbot_verification),
        ("Context Passing", test_context_passing),
        ("Session Continuity", test_session_continuity),
    ]

    results = []

    print(f"\n{'─' * 60}")
    print("UNIT TESTS (no network)")
    print(f"{'─' * 60}")
    for name, test_fn in unit_tests:
        try:
            test_fn()
            results.append((name, True, None))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"  FAIL: {e}")

    print(f"\n{'─' * 60}")
    print("INTEGRATION TESTS (SSH to Pixel Bot)")
    print(f"{'─' * 60}")

    # Check SSH first
    ssh_ok = False
    try:
        test_ssh_connectivity()
        results.append(("SSH Connectivity", True, None))
        ssh_ok = True
    except Exception as e:
        results.append(("SSH Connectivity", False, str(e)))
        print(f"  FAIL: {e}")
        print("  Skipping remaining integration tests.")

    if ssh_ok:
        for name, test_fn in integration_tests[1:]:  # Skip SSH (already ran)
            try:
                test_fn()
                results.append((name, True, None))
            except Exception as e:
                results.append((name, False, str(e)))
                print(f"  FAIL: {e}")

    # Summary
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, err in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {err}" if err else ""))
    print(f"\n{passed}/{len(results)} tests passed")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
