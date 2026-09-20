"""
catalog_search.py
-----------------
Standalone product-search function for the AI Shopping Concierge.

Pipeline:
  1. Filter candidates by category (and connectivity_type for headphones),
     then drop anything priced beyond BUDGET_TOLERANCE above budget.
  2. Normalize dimension scores 0-10 within the filtered candidate set.
  3. Compute budget_fit (0-10).
  4. Compute value_score (0-10, normalized within candidates).
  5. Apply category + priority weight table.
  6. Sort descending by final_score; return top-5 results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Default data-source loader
# ---------------------------------------------------------------------------
_CATALOG_PATH = Path(__file__).parent.parent / "catalog" / "catalog.json"


def load_catalog_json() -> list:
    """Load products from the default catalog.json file."""
    with open(_CATALOG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Weight tables
# ---------------------------------------------------------------------------

# Laptop / Phone  (dimensions: perf, battery, storage, value, budget_fit)
_LAPTOP_PHONE_WEIGHTS = {
    "performance": {"perf": 0.40, "battery": 0.15, "storage": 0.10, "value": 0.20, "budget_fit": 0.15},
    "battery":     {"perf": 0.15, "battery": 0.40, "storage": 0.10, "value": 0.20, "budget_fit": 0.15},
    "value":       {"perf": 0.20, "battery": 0.15, "storage": 0.10, "value": 0.40, "budget_fit": 0.15},
    "balanced":    {"perf": 0.25, "battery": 0.20, "storage": 0.15, "value": 0.20, "budget_fit": 0.20},
}

# Wireless / True-wireless headphones  (dimensions: audio, battery, value, budget_fit)
_WIRELESS_HP_WEIGHTS = {
    "sound_quality": {"audio": 0.45, "battery": 0.20, "value": 0.20, "budget_fit": 0.15},
    "battery":       {"audio": 0.20, "battery": 0.45, "value": 0.20, "budget_fit": 0.15},
    "value":         {"audio": 0.20, "battery": 0.20, "value": 0.45, "budget_fit": 0.15},
    "balanced":      {"audio": 0.30, "battery": 0.25, "value": 0.25, "budget_fit": 0.20},
}

# Wired headphones  (dimensions: audio, value, budget_fit)
_WIRED_HP_WEIGHTS = {
    "sound_quality": {"audio": 0.55, "value": 0.25, "budget_fit": 0.20},
    "value":         {"audio": 0.30, "value": 0.50, "budget_fit": 0.20},
    "balanced":      {"audio": 0.40, "value": 0.35, "budget_fit": 0.25},
}

_WIRED_HP_VALID_PRIORITIES = frozenset(_WIRED_HP_WEIGHTS.keys())
_WIRELESS_HP_VALID_PRIORITIES = frozenset(_WIRELESS_HP_WEIGHTS.keys())
_LAPTOP_PHONE_VALID_PRIORITIES = frozenset(_LAPTOP_PHONE_WEIGHTS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(values):
    """Min-max normalize a list to [0, 10].

    If all values are identical the result is 10.0 for every element
    (avoids division-by-zero and avoids unfairly penalizing a uniform set).
    """
    lo, hi = min(values), max(values)
    if hi == lo:
        return [10.0] * len(values)
    return [(v - lo) / (hi - lo) * 10.0 for v in values]


# ---------------------------------------------------------------------------
# Budget tolerance
# ---------------------------------------------------------------------------
#
# Products priced above budget are not excluded outright — a near-miss is
# often the right recommendation, and a shopper who says "₹60,000" will
# usually look at ₹64,999. Anything beyond this band is dropped, so a
# ₹1.4-lakh laptop can never win a ₹60,000 search on raw performance.
#
# Scoring still penalises overshoot inside the band via _budget_fit, so a
# near-miss has to earn its place on other dimensions. Note that at the
# band edge budget_fit is 10 - 0.15*20 = 7.0, which means the floor at 0.0
# in _budget_fit is unreachable for any product that survives the filter.
BUDGET_TOLERANCE = 0.15


def _within_budget(price, budget):
    """True if price is at or below budget plus the tolerance band."""
    return price <= budget * (1.0 + BUDGET_TOLERANCE)


def _budget_fit(price, budget):
    """Compute budget_fit score in [0, 10]."""
    if price <= budget:
        return 10.0 - (budget - price) / budget * 5.0
    else:
        return max(0.0, 10.0 - (price - budget) / budget * 20.0)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def catalog_search(constraints, data_source=load_catalog_json):
    """
    Search the product catalog and return the top-5 ranked results.

    Parameters
    ----------
    constraints : dict
        Required keys: ``category``, ``budget``, ``priority``
        Optional key:  ``connectivity_type`` (headphones only)
    data_source : callable
        Zero-argument callable that returns a list of product dicts.
        Defaults to ``load_catalog_json`` (reads catalog/catalog.json).

    Returns
    -------
    list[dict]
        Up to 5 product dicts, ranked best-first.  Empty when nothing in the
        category fits the budget band — the caller is expected to tell the
        user no genuine fit exists rather than widen the search silently.
        Each result is augmented with computed scores:
        ``_perf_score_norm``, ``_battery_score_norm``, ``_storage_score_norm``,
        ``_audio_score_norm``, ``_value_score_norm``, ``_budget_fit``, ``final_score``.

    Raises
    ------
    ValueError
        On invalid category, invalid connectivity_type, or invalid priority
        for the given category/connectivity combination.
    """
    # -----------------------------------------------------------------------
    # Validate & extract constraints
    # -----------------------------------------------------------------------
    category = str(constraints.get("category", "")).lower()
    if category not in {"laptop", "phone", "headphones"}:
        raise ValueError(f"Invalid category: {category!r}")

    budget = float(constraints["budget"])
    priority = str(constraints.get("priority", "")).lower()

    connectivity_type = None
    if category == "headphones":
        ct = constraints.get("connectivity_type")
        if ct is None:
            raise ValueError("connectivity_type is required for headphones")
        connectivity_type = str(ct).lower()
        if connectivity_type not in {"wired", "wireless", "true_wireless"}:
            raise ValueError(f"Invalid connectivity_type: {connectivity_type!r}")

    # Validate priority early and select weight table
    if category in {"laptop", "phone"}:
        if priority not in _LAPTOP_PHONE_VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority {priority!r} for {category}. "
                f"Valid: {sorted(_LAPTOP_PHONE_VALID_PRIORITIES)}"
            )
        weights = _LAPTOP_PHONE_WEIGHTS[priority]
    elif connectivity_type == "wired":
        if priority == "battery":
            raise ValueError(
                "'battery' is not a valid priority for wired headphones. "
                "Valid priorities: sound_quality, value, balanced"
            )
        if priority not in _WIRED_HP_VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority {priority!r} for wired headphones. "
                f"Valid: {sorted(_WIRED_HP_VALID_PRIORITIES)}"
            )
        weights = _WIRED_HP_WEIGHTS[priority]
    else:  # wireless or true_wireless
        if priority not in _WIRELESS_HP_VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority {priority!r} for {connectivity_type} headphones. "
                f"Valid: {sorted(_WIRELESS_HP_VALID_PRIORITIES)}"
            )
        weights = _WIRELESS_HP_WEIGHTS[priority]

    # -----------------------------------------------------------------------
    # STEP 1 - Filter candidates
    # -----------------------------------------------------------------------
    all_products = data_source()
    candidates = []
    for p in all_products:
        if p.get("category") != category:
            continue
        if category == "headphones" and p.get("connectivity_type") != connectivity_type:
            continue
        if not _within_budget(p["price"], budget):
            continue
        # Work on a shallow copy so we never mutate source data
        candidates.append(dict(p))

    if not candidates:
        return []

    # -----------------------------------------------------------------------
    # STEP 2 - Normalize dimension scores within the candidate set
    # -----------------------------------------------------------------------
    if category in {"laptop", "phone"}:
        raw_perf = [c["perf_score"] for c in candidates]
        norm_perf = _normalize(raw_perf)
        for c, s in zip(candidates, norm_perf):
            c["_perf_score_norm"] = s

        raw_bat = [c["battery_hours"] for c in candidates]
        norm_bat = _normalize(raw_bat)
        for c, s in zip(candidates, norm_bat):
            c["_battery_score_norm"] = s

        raw_stor = [c["storage_gb"] for c in candidates]
        norm_stor = _normalize(raw_stor)
        for c, s in zip(candidates, norm_stor):
            c["_storage_score_norm"] = s

    elif connectivity_type in {"wireless", "true_wireless"}:
        raw_audio = [c["audio_score"] for c in candidates]
        norm_audio = _normalize(raw_audio)
        for c, s in zip(candidates, norm_audio):
            c["_audio_score_norm"] = s

        raw_bat = [c["battery_hours"] for c in candidates]
        norm_bat = _normalize(raw_bat)
        for c, s in zip(candidates, norm_bat):
            c["_battery_score_norm"] = s

    else:  # wired headphones - no battery dimension
        raw_audio = [c["audio_score"] for c in candidates]
        norm_audio = _normalize(raw_audio)
        for c, s in zip(candidates, norm_audio):
            c["_audio_score_norm"] = s

    # -----------------------------------------------------------------------
    # STEP 3 - Compute budget_fit
    # -----------------------------------------------------------------------
    for c in candidates:
        c["_budget_fit"] = _budget_fit(c["price"], budget)

    # -----------------------------------------------------------------------
    # STEP 4 - Compute raw value, then normalize within candidates
    # -----------------------------------------------------------------------
    if category in {"laptop", "phone"}:
        raw_values = [
            (c["_perf_score_norm"] + c["_battery_score_norm"]) / (c["price"] / 1000)
            for c in candidates
        ]
    elif connectivity_type in {"wireless", "true_wireless"}:
        raw_values = [
            (c["_audio_score_norm"] + c["_battery_score_norm"]) / (c["price"] / 1000)
            for c in candidates
        ]
    else:  # wired
        raw_values = [
            c["_audio_score_norm"] / (c["price"] / 1000)
            for c in candidates
        ]

    norm_values = _normalize(raw_values)
    for c, s in zip(candidates, norm_values):
        c["_value_score_norm"] = s

    # -----------------------------------------------------------------------
    # STEP 5 + 6 - Apply weights, compute final_score, sort, return top 5
    # -----------------------------------------------------------------------
    for c in candidates:
        if category in {"laptop", "phone"}:
            score = (
                weights["perf"]       * c["_perf_score_norm"]
                + weights["battery"]  * c["_battery_score_norm"]
                + weights["storage"]  * c["_storage_score_norm"]
                + weights["value"]    * c["_value_score_norm"]
                + weights["budget_fit"] * c["_budget_fit"]
            )
        elif connectivity_type in {"wireless", "true_wireless"}:
            score = (
                weights["audio"]      * c["_audio_score_norm"]
                + weights["battery"]  * c["_battery_score_norm"]
                + weights["value"]    * c["_value_score_norm"]
                + weights["budget_fit"] * c["_budget_fit"]
            )
        else:  # wired
            score = (
                weights["audio"]    * c["_audio_score_norm"]
                + weights["value"]  * c["_value_score_norm"]
                + weights["budget_fit"] * c["_budget_fit"]
            )
        c["final_score"] = round(score, 6)

    candidates.sort(key=lambda c: c["final_score"], reverse=True)
    return candidates[:5]
