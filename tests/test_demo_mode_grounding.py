# -*- coding: utf-8 -*-
"""
tests/test_demo_mode_grounding.py
---------------------------------
Verifies that the pre-scripted Demo Mode assistant replies in frontend/index.html
are 100% grounded in real catalog data according to agent/verify_grounding.py.
"""

from __future__ import annotations

import pytest

from agent.verify_grounding import verify_grounding
from tools.catalog_search import load_catalog_json


# ---------------------------------------------------------------------------
# Exact strings from frontend/index.html
# ---------------------------------------------------------------------------

DEMO_REPLY_1 = (
    "For dedicated home listening where acoustic separation and audio fidelity matter most, "
    "here are three top-ranked wired options from our catalog:\n\n"
    "1. **Philips SHP9500** (₹6,499) — Open-back design with large 50mm neodymium drivers "
    "delivering an airy, spacious soundstage ideal for home acoustic listening.\n"
    "2. **Audio-Technica ATH-M20x** (₹4,099) — Accurate 40mm studio monitor drivers tuned "
    "for flat, honest sound reproduction and dependable durability within your budget.\n"
    "3. **Sennheiser HD 206** (₹1,490) — Closed-back lightweight build with 36mm drivers; "
    "exceptional value pick that delivers clean sound well below your spending ceiling."
)

DEMO_REPLY_2 = (
    "If all-day battery life is your top requirement for travel and productivity, "
    "here are three standout endurance picks verified from our catalog:\n\n"
    "1. **Apple MacBook Air 13 M4** (₹99,900) — Class-leading efficiency offering up to 18 hours "
    "of battery life with the Apple M4 chip and 16GB RAM, making it the premier choice for on-the-go work.\n"
    "2. **ASUS Zenbook 14 OLED UX3405MA** (₹99,990) — Powered by the Intel Core Ultra 5 125H with an "
    "impressive 15 hours of battery life and a sharp OLED display for extended work sessions.\n"
    "3. **HP Laptop 15s-ey4002AU** (₹64,999) — Well under your budget ceiling with 10 hours of battery "
    "life on the AMD Ryzen 7 7730U and 16GB RAM for dependable endurance at great value."
)

DEMO_REPLY_3 = (
    '"Cheap" can mean very different things depending on your preferred style and listening habits. '
    "Before I pull up catalog recommendations:\n\n"
    "Are you looking for **wired headphones** for desktop/plugged-in listening (which start around "
    "₹1,000–₹1,500), or **wireless/true wireless earbuds** for mobile convenience (typically "
    "₹1,500–₹3,000)? Also, do you have a specific maximum budget in rupees?"
)


@pytest.fixture(scope="module")
def catalog_map():
    """Map of product_id -> product_dict from real catalog.json."""
    catalog = load_catalog_json()
    return {p["id"]: p for p in catalog}


def test_demo_1_wired_headphones_grounding(catalog_map):
    """Demo 1 (Wired headphones for home listening) must pass verify_grounding with 0 issues."""
    matched_ids = ["headphones_04", "headphones_03", "headphones_02"]
    products = [catalog_map[pid] for pid in matched_ids]

    issues = verify_grounding(DEMO_REPLY_1, products)

    if issues:
        print("\n[FAILED] Demo 1 Grounding Issues:")
        for idx, issue in enumerate(issues, 1):
            print(f"  {idx}. Product: {issue.get('product')}")
            print(f"     Claim:   {issue.get('claim')}")
            print(f"     Issue:   {issue.get('issue')}")

    assert issues == [], f"Demo 1 reply has grounding issues: {issues}"


def test_demo_2_battery_laptop_grounding(catalog_map):
    """Demo 2 (Battery-focused laptop) must pass verify_grounding with 0 issues."""
    matched_ids = ["laptop_15", "laptop_13", "laptop_07"]
    products = [catalog_map[pid] for pid in matched_ids]

    issues = verify_grounding(DEMO_REPLY_2, products)

    if issues:
        print("\n[FAILED] Demo 2 Grounding Issues:")
        for idx, issue in enumerate(issues, 1):
            print(f"  {idx}. Product: {issue.get('product')}")
            print(f"     Claim:   {issue.get('claim')}")
            print(f"     Issue:   {issue.get('issue')}")

    assert issues == [], f"Demo 2 reply has grounding issues: {issues}"


def test_demo_3_clarifying_question_grounding():
    """Demo 3 (Clarifying question for cheap headphones) must pass verify_grounding with 0 issues."""
    # Clarifying question turn has no retrieved products
    issues = verify_grounding(DEMO_REPLY_3, [])

    if issues:
        print("\n[FAILED] Demo 3 Grounding Issues:")
        for idx, issue in enumerate(issues, 1):
            print(f"  {idx}. Product: {issue.get('product')}")
            print(f"     Claim:   {issue.get('claim')}")
            print(f"     Issue:   {issue.get('issue')}")

    assert issues == [], f"Demo 3 reply has grounding issues: {issues}"


if __name__ == "__main__":
    pytest.main(["-v", "-s", __file__])
