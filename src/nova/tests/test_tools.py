#!/usr/bin/env python3
"""
Tool Tests — Unit tests for all 4 active Nova tools.

Tests:
- SystemStatsTool: All stat types
- ClipboardTool: Read/write actions
- TimerTool: Set/list/cancel/check + duration parsing
- NotesTool: Add/list/search/delete
- BaseTool: Abstract interface

Run: python -m nova.tests.test_tools
"""
import sys
import os
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nova.tools import SystemStatsTool, ClipboardTool, TimerTool, NotesTool
from nova.tools.base import BaseTool


# ============================================================================
# BaseTool Tests
# ============================================================================

def test_base_tool_abstract():
    """BaseTool cannot be instantiated directly."""
    print("\n=== Test: BaseTool Abstract ===")
    try:
        BaseTool()
        assert False, "Should not be able to instantiate BaseTool"
    except TypeError:
        pass
    print("  Cannot instantiate abstract class: OK")
    print("  PASS")


def test_base_tool_repr():
    """BaseTool repr uses tool name."""
    print("\n=== Test: BaseTool repr ===")
    tool = SystemStatsTool()
    assert "system_stats" in repr(tool)
    print(f"  repr: {repr(tool)}")
    print("  PASS")


# ============================================================================
# SystemStatsTool Tests
# ============================================================================

def test_system_stats_cpu():
    """CPU stats return usage and cores."""
    print("\n=== Test: SystemStats CPU ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="cpu")
    assert "CPU Usage" in result
    assert "CPU Cores" in result
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_memory():
    """Memory stats return RAM and swap."""
    print("\n=== Test: SystemStats Memory ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="memory")
    assert "RAM" in result
    assert "GB" in result
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_gpu():
    """GPU stats return usage or unavailable message."""
    print("\n=== Test: SystemStats GPU ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="gpu")
    assert "GPU" in result or "unavailable" in result.lower()
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_disk():
    """Disk stats return usage."""
    print("\n=== Test: SystemStats Disk ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="disk")
    assert "Disk" in result
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_temperature():
    """Temperature stats return values or unavailable message."""
    print("\n=== Test: SystemStats Temperature ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="temperature")
    assert "Temperature" in result or "not available" in result.lower()
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_processes():
    """Process stats return sorted list."""
    print("\n=== Test: SystemStats Processes ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="processes")
    assert "processes" in result.lower() or "PID" in result
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_overview():
    """Overview returns CPU, RAM, disk summary."""
    print("\n=== Test: SystemStats Overview ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="overview")
    assert "CPU" in result
    assert "RAM" in result
    assert "Disk" in result
    print(f"  {result.splitlines()[0]}")
    print("  PASS")


def test_system_stats_invalid_type():
    """Invalid stat type returns error."""
    print("\n=== Test: SystemStats Invalid Type ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="invalid")
    assert "ERROR" in result
    print("  PASS")


def test_system_stats_process_filter():
    """Process name filter works."""
    print("\n=== Test: SystemStats Process Filter ===")
    tool = SystemStatsTool()
    result = tool.execute(stat_type="processes", process_name="python", limit=3)
    assert "python" in result.lower() or "No processes found" in result
    print("  PASS")


# ============================================================================
# ClipboardTool Tests
# ============================================================================

def test_clipboard_invalid_action():
    """Invalid action returns error."""
    print("\n=== Test: Clipboard Invalid Action ===")
    tool = ClipboardTool()
    result = tool.execute(action="invalid")
    assert "ERROR" in result
    print("  PASS")


def test_clipboard_write_empty():
    """Writing empty text returns error."""
    print("\n=== Test: Clipboard Write Empty ===")
    tool = ClipboardTool()
    result = tool.execute(action="write", text="")
    assert "ERROR" in result
    print("  PASS")


def test_clipboard_read():
    """Read clipboard returns content or empty message."""
    print("\n=== Test: Clipboard Read ===")
    tool = ClipboardTool()
    result = tool.execute(action="read")
    assert "Clipboard" in result or "ERROR" in result
    print("  PASS")


# ============================================================================
# TimerTool Tests
# ============================================================================

def test_timer_duration_parsing():
    """Timer parses various duration formats."""
    print("\n=== Test: Timer Duration Parsing ===")
    tool = TimerTool()

    cases = [
        ("5m", 300),
        ("30s", 30),
        ("1h", 3600),
        ("90", 90),
        ("2.5m", 150),
        ("0.5h", 1800),
        ("10", 10),
        ("1hour", 3600),
    ]

    passed = 0
    for duration_str, expected in cases:
        result = tool._parse_duration(duration_str)
        if result == expected:
            passed += 1
        else:
            print(f"  FAIL: _parse_duration('{duration_str}') = {result}, expected {expected}")

    print(f"  {passed}/{len(cases)} passed")
    assert passed == len(cases), f"Duration parsing failures"
    print("  PASS")


def test_timer_invalid_duration():
    """Invalid duration returns None."""
    print("\n=== Test: Timer Invalid Duration ===")
    tool = TimerTool()
    assert tool._parse_duration("") is None
    assert tool._parse_duration("abc") is None
    print("  PASS")


def test_timer_set_and_list():
    """Set a timer and verify it appears in list."""
    print("\n=== Test: Timer Set & List ===")
    tool = TimerTool()

    result = tool.execute(action="set", duration="60s", timer_name="test-set-list")
    assert "test-set-list" in result
    assert "set for" in result.lower()

    result = tool.execute(action="list")
    assert "test-set-list" in result

    # Cleanup
    tool.execute(action="cancel", timer_name="test-set-list")
    print("  PASS")


def test_timer_cancel():
    """Cancel a running timer."""
    print("\n=== Test: Timer Cancel ===")
    tool = TimerTool()

    tool.execute(action="set", duration="120s", timer_name="test-cancel")
    result = tool.execute(action="cancel", timer_name="test-cancel")
    assert "cancelled" in result.lower()

    result = tool.execute(action="cancel", timer_name="test-cancel")
    assert "not found" in result.lower() or "ERROR" in result
    print("  PASS")


def test_timer_check():
    """Check remaining time on a timer."""
    print("\n=== Test: Timer Check ===")
    tool = TimerTool()

    tool.execute(action="set", duration="120s", timer_name="test-check")
    result = tool.execute(action="check", timer_name="test-check")
    assert "remaining" in result.lower()

    # Cleanup
    tool.execute(action="cancel", timer_name="test-check")
    print("  PASS")


def test_timer_invalid_action():
    """Invalid timer action returns error."""
    print("\n=== Test: Timer Invalid Action ===")
    tool = TimerTool()
    result = tool.execute(action="invalid")
    assert "ERROR" in result
    print("  PASS")


def test_timer_max_duration():
    """Timer rejects duration over 24 hours."""
    print("\n=== Test: Timer Max Duration ===")
    tool = TimerTool()
    result = tool.execute(action="set", duration="25h")
    assert "ERROR" in result
    print("  PASS")


# ============================================================================
# NotesTool Tests
# ============================================================================

def test_notes_add():
    """Add a note and verify it saves."""
    print("\n=== Test: Notes Add ===")
    tool = NotesTool()
    result = tool.execute(action="add", content="Test note from unit test")
    assert "saved" in result.lower()
    print(f"  {result}")
    print("  PASS")


def test_notes_add_empty():
    """Adding empty note returns error."""
    print("\n=== Test: Notes Add Empty ===")
    tool = NotesTool()
    result = tool.execute(action="add", content="")
    assert "ERROR" in result
    print("  PASS")


def test_notes_list():
    """List notes returns results."""
    print("\n=== Test: Notes List ===")
    tool = NotesTool()
    result = tool.execute(action="list")
    # Either has notes or says no notes
    assert "Notes" in result or "No notes" in result
    print("  PASS")


def test_notes_search():
    """Search finds matching notes."""
    print("\n=== Test: Notes Search ===")
    tool = NotesTool()
    # Add a searchable note
    tool.execute(action="add", content="UNIQUE_SEARCH_TOKEN_12345")
    result = tool.execute(action="search", content="UNIQUE_SEARCH_TOKEN_12345")
    assert "Found" in result or "UNIQUE_SEARCH_TOKEN" in result
    print("  PASS")


def test_notes_search_empty():
    """Search with empty query returns error."""
    print("\n=== Test: Notes Search Empty ===")
    tool = NotesTool()
    result = tool.execute(action="search", query="")
    assert "ERROR" in result
    print("  PASS")


def test_notes_invalid_action():
    """Invalid notes action returns error."""
    print("\n=== Test: Notes Invalid Action ===")
    tool = NotesTool()
    result = tool.execute(action="invalid")
    assert "ERROR" in result
    print("  PASS")


# ============================================================================
# Runner
# ============================================================================

def main():
    print("=" * 60)
    print("NOVA TOOL TESTS")
    print("=" * 60)

    tests = [
        # BaseTool
        ("BaseTool Abstract", test_base_tool_abstract),
        ("BaseTool repr", test_base_tool_repr),
        # SystemStats
        ("SystemStats CPU", test_system_stats_cpu),
        ("SystemStats Memory", test_system_stats_memory),
        ("SystemStats GPU", test_system_stats_gpu),
        ("SystemStats Disk", test_system_stats_disk),
        ("SystemStats Temperature", test_system_stats_temperature),
        ("SystemStats Processes", test_system_stats_processes),
        ("SystemStats Overview", test_system_stats_overview),
        ("SystemStats Invalid Type", test_system_stats_invalid_type),
        ("SystemStats Process Filter", test_system_stats_process_filter),
        # Clipboard
        ("Clipboard Invalid Action", test_clipboard_invalid_action),
        ("Clipboard Write Empty", test_clipboard_write_empty),
        ("Clipboard Read", test_clipboard_read),
        # Timer
        ("Timer Duration Parsing", test_timer_duration_parsing),
        ("Timer Invalid Duration", test_timer_invalid_duration),
        ("Timer Set & List", test_timer_set_and_list),
        ("Timer Cancel", test_timer_cancel),
        ("Timer Check", test_timer_check),
        ("Timer Invalid Action", test_timer_invalid_action),
        ("Timer Max Duration", test_timer_max_duration),
        # Notes
        ("Notes Add", test_notes_add),
        ("Notes Add Empty", test_notes_add_empty),
        ("Notes List", test_notes_list),
        ("Notes Search", test_notes_search),
        ("Notes Search Empty", test_notes_search_empty),
        ("Notes Invalid Action", test_notes_invalid_action),
    ]

    results = []
    for name, test_fn in tests:
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
