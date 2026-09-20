# -*- coding: utf-8 -*-
"""
tests/test_server_products.py
-----------------------------
Isolated unit tests for the get_latest_retrieved_products() helper in api/server.py.
Uses mock Anthropic ContentBlock objects and message structures.
"""

from __future__ import annotations

import os
import sys

import pytest

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from api.server import get_latest_retrieved_products


# ---------------------------------------------------------------------------
# Mock ContentBlock class (mimicking Anthropic SDK objects)
# ---------------------------------------------------------------------------

class FakeBlock:
    """Mock object with attributes to match Anthropic's block classes in API replies."""
    def __init__(self, type_val: str, name_val: str | None = None, id_val: str | None = None):
        self.type = type_val
        self.name = name_val
        self.id = id_val


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_matching_catalog_search():
    """Verify clean catalog_search tool results are parsed and returned correctly."""
    messages = [
        {
            "role": "assistant",
            "content": [
                FakeBlock(type_val="tool_use", name_val="catalog_search", id_val="call_123")
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": '[{"id": "laptop_01", "name": "ASUS TUF", "price": 55000}]'
                }
            ]
        }
    ]

    results = get_latest_retrieved_products(messages)
    assert len(results) == 1
    assert results[0]["id"] == "laptop_01"
    assert results[0]["name"] == "ASUS TUF"
    assert results[0]["price"] == 55000


def test_no_tool_calls():
    """Verify empty lists are returned when no tools exist in message logs."""
    messages = [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "how can I assist you today?"}
    ]

    results = get_latest_retrieved_products(messages)
    assert results == []


def test_ignore_other_tool_calls():
    """Verify tool calls like parse_constraints are ignored, falling back appropriately."""
    messages = [
        # Earlier matching catalog_search call
        {
            "role": "assistant",
            "content": [
                FakeBlock(type_val="tool_use", name_val="catalog_search", id_val="call_111")
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_111",
                    "content": '[{"id": "laptop_01", "name": "ASUS TUF", "price": 55000}]'
                }
            ]
        },
        # More recent parse_constraints call
        {
            "role": "assistant",
            "content": [
                FakeBlock(type_val="tool_use", name_val="parse_constraints", id_val="call_222")
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_222",
                    "content": '{"category": "laptop"}'
                }
            ]
        }
    ]

    results = get_latest_retrieved_products(messages)
    # Must skip parse_constraints and extract the earlier catalog_search products
    assert len(results) == 1
    assert results[0]["id"] == "laptop_01"


def test_multiple_catalog_searches_returns_latest():
    """Verify search scans backward and returns ONLY the products from the last search."""
    messages = [
        # First search
        {
            "role": "assistant",
            "content": [
                FakeBlock(type_val="tool_use", name_val="catalog_search", id_val="call_first")
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_first",
                    "content": '[{"id": "laptop_old", "name": "Old Lenovo"}]'
                }
            ]
        },
        # Second search
        {
            "role": "assistant",
            "content": [
                FakeBlock(type_val="tool_use", name_val="catalog_search", id_val="call_second")
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_second",
                    "content": '[{"id": "laptop_new", "name": "New Lenovo"}]'
                }
            ]
        }
    ]

    results = get_latest_retrieved_products(messages)
    assert len(results) == 1
    assert results[0]["id"] == "laptop_new"
    assert results[0]["name"] == "New Lenovo"


def test_malformed_json_fallback():
    """Verify that unparseable or bad JSON content returns [] instead of crashing."""
    messages = [
        {
            "role": "assistant",
            "content": [
                FakeBlock(type_val="tool_use", name_val="catalog_search", id_val="call_bad")
            ]
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_bad",
                    "content": "{invalid-json-string}"
                }
            ]
        }
    ]

    # Must catch JSONDecodeError gracefully
    results = get_latest_retrieved_products(messages)
    assert results == []
