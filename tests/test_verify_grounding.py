# -*- coding: utf-8 -*-
"""
tests/test_verify_grounding.py
------------------------------
Tests for verify_grounding() against the Eval Plan golden cases.

Coverage:
  G11  wrong battery number (9 hours claimed as 18)          -> must catch
  G12  product_id not present in retrieved data              -> must catch
  G22  battery claimed for a WIRED headphone                 -> must catch
       as a STRUCTURAL violation, not a value mismatch
  NEW  RTX 4060 claimed for a laptop whose gpu_model is
       RTX 3050                                              -> must catch
  CLEAN  two real transcripts captured from the orchestrator
       on 2026-08-29, verified accurate by hand               -> no issues

The clean cases matter as much as the catch cases: a grounding gate that
fires on correct responses would either be switched off or would train the
orchestrator to strip useful detail.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.verify_grounding import verify_grounding


# ---------------------------------------------------------------------------
# Fixtures — real catalog rows, exactly as catalog_search returns them
# ---------------------------------------------------------------------------

LAPTOP_07 = {
    "id": "laptop_07",
    "name": "HP Laptop 15s-ey4002AU (AMD Ryzen 7 7730U, 16GB, 512GB SSD, 15.6 FHD)",
    "category": "laptop", "price": 64999, "avg_rating": 4.2,
    "review_count": 4100, "warranty_months": 12,
    "processor": "AMD Ryzen 7 7730U", "ram_gb": 16, "battery_hours": 10,
    "storage_gb": 512, "storage_type": "SSD", "graphics_type": "integrated",
    "gpu_model": None, "perf_score": 4.93,
}
LAPTOP_06 = {
    "id": "laptop_06",
    "name": "Lenovo IdeaPad Slim 3 (AMD Ryzen 5 7530U, 16GB, 512GB SSD, 15.6 FHD)",
    "category": "laptop", "price": 59990, "avg_rating": 4.3,
    "review_count": 5400, "warranty_months": 12,
    "processor": "AMD Ryzen 5 7530U", "ram_gb": 16, "battery_hours": 9,
    "storage_gb": 512, "storage_type": "SSD", "graphics_type": "integrated",
    "gpu_model": None, "perf_score": 4.48,
}
LAPTOP_08 = {
    "id": "laptop_08",
    "name": "ASUS TUF Gaming A15 FA506ICB (AMD Ryzen 7 4800H, 16GB, 512GB SSD, RTX 3050)",
    "category": "laptop", "price": 67990, "avg_rating": 4.4,
    "review_count": 18700, "warranty_months": 12,
    "processor": "AMD Ryzen 7 4800H", "ram_gb": 16, "battery_hours": 8,
    "storage_gb": 512, "storage_type": "SSD", "graphics_type": "dedicated",
    "gpu_model": "RTX 3050", "perf_score": 5.13,
}
LAPTOP_05 = {
    "id": "laptop_05",
    "name": "ASUS VivoBook 15 X1504ZA (Intel Core i5-1235U, 16GB, 512GB SSD, 15.6 FHD OLED)",
    "category": "laptop", "price": 57990, "avg_rating": 4.3,
    "review_count": 7200, "warranty_months": 12,
    "processor": "Intel Core i5-1235U", "ram_gb": 16, "battery_hours": 9,
    "storage_gb": 512, "storage_type": "SSD", "graphics_type": "integrated",
    "gpu_model": None, "perf_score": 3.71,
}
LAPTOP_04 = {
    "id": "laptop_04",
    "name": "Dell Inspiron 15 3520 (Intel Core i5-1235U, 16GB, 512GB SSD, 15.6 FHD)",
    "category": "laptop", "price": 56990, "avg_rating": 4.3,
    "review_count": 15600, "warranty_months": 12,
    "processor": "Intel Core i5-1235U", "ram_gb": 16, "battery_hours": 8,
    "storage_gb": 512, "storage_type": "SSD", "graphics_type": "integrated",
    "gpu_model": None, "perf_score": 3.71,
}

G01_PRODUCTS = [LAPTOP_07, LAPTOP_06, LAPTOP_08, LAPTOP_05, LAPTOP_04]

# Wired headphones — note the ABSENCE of battery_hours, not a zero value.
HP_02 = {
    "id": "headphones_02",
    "name": "Sennheiser HD 206 (Wired Over-Ear, Closed-Back, 36mm Driver, 3.5mm/6.3mm)",
    "category": "headphones", "price": 1490, "avg_rating": 4.3,
    "review_count": 28700, "warranty_months": 24, "connectivity_type": "wired",
    "noise_cancellation": "passive", "codec_support": "N/A",
    "driver_size_mm": 36, "frequency_response_available": True,
    "audio_score": 8.33,
}
HP_05 = {
    "id": "headphones_05",
    "name": "Sony MDR-ZX310AP (Wired On-Ear, 30mm Driver, 3.5mm, Foldable, Mic)",
    "category": "headphones", "price": 1390, "avg_rating": 4.2,
    "review_count": 22300, "warranty_months": 12, "connectivity_type": "wired",
    "noise_cancellation": "passive", "codec_support": "N/A",
    "driver_size_mm": 30, "frequency_response_available": True,
    "audio_score": 7.85,
}
HP_06 = {
    "id": "headphones_06",
    "name": "JBL Tune 500 (Wired On-Ear, 32mm Driver, 3.5mm, Pure Bass, Mic, Foldable)",
    "category": "headphones", "price": 999, "avg_rating": 4.2,
    "review_count": 49000, "warranty_months": 12, "connectivity_type": "wired",
    "noise_cancellation": "passive", "codec_support": "N/A",
    "driver_size_mm": 32, "frequency_response_available": False,
    "audio_score": 6.47,
}
HP_01 = {
    "id": "headphones_01",
    "name": "boAt BassHeads 100 (Wired In-Ear, 10mm Driver, 3.5mm, HD Mic)",
    "category": "headphones", "price": 399, "avg_rating": 4.1,
    "review_count": 95000, "warranty_months": 12, "connectivity_type": "wired",
    "noise_cancellation": "passive", "codec_support": "N/A",
    "driver_size_mm": 10, "frequency_response_available": False,
    "audio_score": 5.04,
}

G19_PRODUCTS = [HP_02, HP_05, HP_06, HP_01]

# True wireless — battery_hours DOES exist here.
HP_16 = {
    "id": "headphones_16",
    "name": "Samsung Galaxy Buds FE (True Wireless, 11mm, BT 5.2, ANC, 6hr Buds + 21hr Case)",
    "category": "headphones", "price": 3999, "avg_rating": 4.3,
    "review_count": 26000, "warranty_months": 12,
    "connectivity_type": "true_wireless", "noise_cancellation": "anc",
    "codec_support": "SBC", "driver_size_mm": 11, "battery_hours": 6,
    "audio_score": 6.41,
}


# ---------------------------------------------------------------------------
# Real transcripts (captured 2026-08-29, hand-verified accurate)
# ---------------------------------------------------------------------------

CLEAN_LAPTOP_DRAFT = """Here are the three worth your attention — note two come in over ₹60k, so flagging that up front:

**1. Lenovo IdeaPad Slim 3 — ₹59,990** (the only one actually in budget)
Ryzen 5 7530U + 16GB RAM handles 1080p timelines without stuttering. It's the strongest performer you can get without going over your number.

**2. ASUS TUF Gaming A15 — ₹67,990** (₹8k over)
The only one here with a dedicated GPU (RTX 3050). For video editing that's the real unlock — hardware-accelerated exports and effects previews that integrated graphics just grind through. If you can stretch, this is the performance pick.

**3. HP 15s (Ryzen 7 7730U) — ₹64,999** (₹5k over)
Fastest CPU of the integrated-graphics bunch. Faster than the Lenovo on raw processing, but without a GPU it won't beat the TUF on actual export times.

**My take:** if ₹60k is a hard ceiling, take the Lenovo. If it's soft, the TUF A15 is the one — for video editing specifically, the dedicated GPU does more for you than any CPU bump in this range. Which way is your budget leaning?"""

CLEAN_WIRED_DRAFT = """Here are your top 3:

**1. Sennheiser HD 206 — ₹1,490**
The clear sound-quality pick. Big 36mm drivers in a closed-back over-ear design — the format that actually gets you full, unfatiguing sound for long listening sessions at home. Also comes with a 2-year warranty, double the others.

**2. Sony MDR-ZX310AP — ₹1,390**
Close second on sound, but it's on-ear rather than over-ear — slightly less room for the sound to breathe, and more ear pressure over a long album session at home.

**3. JBL Tune 500 — ₹999**
Noticeably a step down in audio quality; its tuning leans bass-heavy rather than balanced. Only worth it if you'd rather save ₹500.

For music at home with sound quality as your priority, take the **HD 206** — it's ₹100 more than the Sony and the over-ear build is the difference you'll actually hear and feel."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue_text(issues):
    return " | ".join(f"{i['product']}::{i['claim']}::{i['issue']}" for i in issues)


# ---------------------------------------------------------------------------
# G11 — wrong battery value
# ---------------------------------------------------------------------------

class TestG11WrongBatteryValue:
    """Draft claims 18-hour battery; catalog says 9. Must catch."""

    DRAFT = (
        "**Lenovo IdeaPad Slim 3 — ₹59,990**\n"
        "Great pick for travel — you get 18 hours of battery, so it lasts a "
        "full working day unplugged."
    )

    def test_mismatch_is_caught(self):
        issues = verify_grounding(self.DRAFT, [LAPTOP_06])
        battery = [i for i in issues if "battery" in i["issue"].lower()]
        assert battery, f"18h vs 9h not caught. Got: {_issue_text(issues)}"

    def test_issue_names_both_numbers(self):
        issues = verify_grounding(self.DRAFT, [LAPTOP_06])
        text = _issue_text(issues)
        assert "18" in text and "9" in text, f"issue should cite both: {text}"

    def test_attributed_to_the_right_product(self):
        issues = verify_grounding(self.DRAFT, [LAPTOP_06])
        assert any(i["product"] == LAPTOP_06["name"] for i in issues)

    def test_correct_value_passes(self):
        """The same sentence with the real number must not fire."""
        clean = self.DRAFT.replace("18 hours", "9 hours")
        assert verify_grounding(clean, [LAPTOP_06]) == []

    def test_right_number_wrong_product_is_caught(self):
        """9h is real for the Lenovo but not for the TUF (8h).

        This is the check that distinguishes real field-matching from
        'the value exists somewhere in the catalog'.
        """
        draft = (
            "**ASUS TUF Gaming A15 — ₹67,990**\n"
            "Solid all-rounder with 9 hours of battery."
        )
        issues = verify_grounding(draft, [LAPTOP_08, LAPTOP_06])
        assert any(i["product"] == LAPTOP_08["name"] and "battery" in i["issue"]
                   for i in issues), (
            f"9h borrowed from another product not caught: {_issue_text(issues)}"
        )


# ---------------------------------------------------------------------------
# G12 — unknown product reference
# ---------------------------------------------------------------------------

class TestG12UnknownProductId:
    """Draft references a product_id not in retrieved_products. Must catch."""

    def test_unknown_id_is_caught(self):
        draft = (
            "**Lenovo IdeaPad Slim 3 — ₹59,990**\n"
            "Also consider laptop_18, which is a stronger performer."
        )
        issues = verify_grounding(draft, [LAPTOP_06])
        assert any("laptop_18" in i["claim"] for i in issues), (
            f"unknown id not caught: {_issue_text(issues)}"
        )

    def test_known_id_does_not_fire(self):
        draft = "**Lenovo IdeaPad Slim 3 — ₹59,990** (laptop_06) is the pick."
        ids = [i for i in verify_grounding(draft, [LAPTOP_06])
               if "not in the retrieved data" in i["issue"]]
        assert ids == [], f"known id wrongly flagged: {_issue_text(ids)}"

    def test_unknown_id_is_unattributed(self):
        draft = "Consider headphones_99 instead."
        issues = verify_grounding(draft, [HP_02])
        unknown = [i for i in issues if "headphones_99" in i["claim"]]
        assert unknown and unknown[0]["product"] is None

    @pytest.mark.parametrize("bad_id", ["laptop_18", "phone_03", "headphones_99"])
    def test_all_id_shapes(self, bad_id):
        issues = verify_grounding(f"Try {bad_id}.", [LAPTOP_06])
        assert any(bad_id in i["claim"] for i in issues)


# ---------------------------------------------------------------------------
# G22 — structural violation
# ---------------------------------------------------------------------------

class TestG22StructuralBatteryOnWired:
    """Battery claimed for a wired headphone — no such field exists.

    The pass criterion is specifically that this is caught as a STRUCTURAL
    violation (the field cannot exist for this category), not merely as a
    wrong number.
    """

    DRAFT = (
        "**Sennheiser HD 206 — ₹1,490**\n"
        "Excellent sound, and you get 12 hours of battery life on a charge."
    )

    def test_violation_is_caught(self):
        issues = verify_grounding(self.DRAFT, [HP_02])
        assert issues, "structural violation not caught at all"

    def test_flagged_as_structural_not_value_mismatch(self):
        issues = verify_grounding(self.DRAFT, [HP_02])
        structural = [i for i in issues if "structural" in i["issue"].lower()]
        assert structural, (
            f"caught, but not as structural: {_issue_text(issues)}"
        )
        assert not any("mismatch" in i["issue"].lower() for i in issues), (
            "a wired battery claim must not also be reported as a value "
            f"mismatch: {_issue_text(issues)}"
        )

    def test_issue_explains_the_field_does_not_exist(self):
        issues = verify_grounding(self.DRAFT, [HP_02])
        assert any("battery_hours" in i["issue"] for i in issues)

    def test_fires_without_a_number_attached(self):
        """'all-day battery' has no number to mismatch, but is still wrong."""
        draft = (
            "**Sennheiser HD 206 — ₹1,490**\n"
            "Great sound and superb battery life for the price."
        )
        issues = verify_grounding(draft, [HP_02])
        assert any("structural" in i["issue"].lower() for i in issues), (
            f"numberless battery claim not caught: {_issue_text(issues)}"
        )

    def test_same_claim_is_fine_for_true_wireless(self):
        """6 hours IS correct for the Galaxy Buds — must not fire."""
        draft = (
            "**Samsung Galaxy Buds FE — ₹3,999**\n"
            "Gets you 6 hours of battery on the buds themselves."
        )
        assert verify_grounding(draft, [HP_16]) == []

    def test_wrong_number_still_caught_for_true_wireless(self):
        draft = (
            "**Samsung Galaxy Buds FE — ₹3,999**\n"
            "Gets you 11 hours of battery on the buds themselves."
        )
        issues = verify_grounding(draft, [HP_16])
        assert any("battery mismatch" in i["issue"].lower() for i in issues)


# ---------------------------------------------------------------------------
# NEW — GPU model mismatch
# ---------------------------------------------------------------------------

class TestGpuModelMismatch:
    """Draft claims RTX 4060; the laptop's gpu_model is RTX 3050."""

    DRAFT = (
        "**ASUS TUF Gaming A15 — ₹67,990**\n"
        "The dedicated RTX 4060 hardware-accelerates your exports."
    )

    def test_mismatch_is_caught(self):
        issues = verify_grounding(self.DRAFT, [LAPTOP_08])
        assert any("gpu" in i["issue"].lower() for i in issues), (
            f"GPU mismatch not caught: {_issue_text(issues)}"
        )

    def test_issue_names_both_models(self):
        issues = verify_grounding(self.DRAFT, [LAPTOP_08])
        text = _issue_text(issues)
        assert "RTX 4060" in text and "RTX 3050" in text

    def test_correct_gpu_passes(self):
        clean = self.DRAFT.replace("RTX 4060", "RTX 3050")
        assert verify_grounding(clean, [LAPTOP_08]) == []

    def test_gpu_claimed_for_integrated_laptop(self):
        """gpu_model is null — any GPU claim is unsupported."""
        draft = (
            "**Lenovo IdeaPad Slim 3 — ₹59,990**\n"
            "The RTX 3050 makes short work of exports."
        )
        issues = verify_grounding(draft, [LAPTOP_06])
        assert any("null" in i["issue"] or "integrated" in i["issue"]
                   for i in issues), (
            f"GPU on integrated laptop not caught: {_issue_text(issues)}"
        )

    def test_gpu_borrowed_from_another_retrieved_product(self):
        """RTX 3050 is real for the TUF but not for the Dell.

        Both products are in the retrieved set, so a checker that only asked
        'does this string appear in the catalog' would pass this draft.
        """
        draft = (
            "**Dell Inspiron 15 3520 — ₹56,990**\n"
            "Comes with an RTX 3050 for accelerated exports.\n\n"
            "**ASUS TUF Gaming A15 — ₹67,990**\n"
            "Also has the RTX 3050."
        )
        issues = verify_grounding(draft, [LAPTOP_04, LAPTOP_08])
        dell = [i for i in issues if i["product"] == LAPTOP_04["name"]]
        tuf = [i for i in issues if i["product"] == LAPTOP_08["name"]]
        assert dell, f"borrowed GPU not caught on the Dell: {_issue_text(issues)}"
        assert not tuf, f"TUF's correct GPU wrongly flagged: {_issue_text(tuf)}"


# ---------------------------------------------------------------------------
# Clean cases — real transcripts, no false positives
# ---------------------------------------------------------------------------

class TestCleanTranscripts:
    """Accurate real responses must produce an empty issue list."""

    def test_clean_laptop_transcript(self):
        issues = verify_grounding(CLEAN_LAPTOP_DRAFT, G01_PRODUCTS)
        assert issues == [], f"false positives: {_issue_text(issues)}"

    def test_clean_wired_transcript(self):
        """Includes 'save ₹500' and '₹100 more than' — deltas, not prices."""
        issues = verify_grounding(CLEAN_WIRED_DRAFT, G19_PRODUCTS)
        assert issues == [], f"false positives: {_issue_text(issues)}"

    def test_clean_wired_transcript_mentions_no_battery(self):
        """Guard on the fixture itself, per G19's own pass criterion."""
        assert "batter" not in CLEAN_WIRED_DRAFT.lower()

    def test_corrupting_one_price_breaks_the_clean_laptop_case(self):
        """Confirms the clean case is sensitive, not vacuously passing."""
        corrupted = CLEAN_LAPTOP_DRAFT.replace("₹59,990", "₹52,990")
        issues = verify_grounding(corrupted, G01_PRODUCTS)
        assert any("price mismatch" in i["issue"] for i in issues), (
            f"corrupted price not caught: {_issue_text(issues)}"
        )

    def test_corrupting_one_ram_figure_breaks_the_clean_laptop_case(self):
        corrupted = CLEAN_LAPTOP_DRAFT.replace("16GB RAM", "32GB RAM")
        issues = verify_grounding(corrupted, G01_PRODUCTS)
        assert any("RAM mismatch" in i["issue"] for i in issues), (
            f"corrupted RAM not caught: {_issue_text(issues)}"
        )

    def test_injecting_battery_into_the_wired_transcript_is_caught(self):
        corrupted = CLEAN_WIRED_DRAFT.replace(
            "Big 36mm drivers", "Big 36mm drivers and 20 hours of battery"
        )
        issues = verify_grounding(corrupted, G19_PRODUCTS)
        assert any("structural" in i["issue"].lower() for i in issues)


# ---------------------------------------------------------------------------
# Delta amounts and segmentation
# ---------------------------------------------------------------------------

class TestDeltaAmountsAreNotPriceClaims:
    """Savings and gaps must not be read as price claims.

    Without this the gate produces false positives on well-written
    responses, which is the fastest way to get a grounding check disabled.
    """

    @pytest.mark.parametrize("body", [
        "Only worth it if you'd rather save ₹500.",
        "It's ₹100 more than the Sony.",
        "That's ₹8,000 over your ceiling.",
        "You'd spend another ₹5,000 for it.",
    ])
    def test_delta_phrasings_do_not_fire(self, body):
        draft = f"**JBL Tune 500 — ₹999**\n{body}"
        issues = verify_grounding(draft, [HP_06])
        prices = [i for i in issues if "price" in i["issue"].lower()]
        assert prices == [], f"delta read as a price claim: {_issue_text(prices)}"

    def test_shorthand_amounts_do_not_fire(self):
        draft = "**JBL Tune 500 — ₹999**\nWell under your ₹3k ceiling."
        assert verify_grounding(draft, [HP_06]) == []

    def test_a_real_wrong_price_still_fires(self):
        draft = "**JBL Tune 500 — ₹1,299**\nGood value."
        issues = verify_grounding(draft, [HP_06])
        assert any("price mismatch" in i["issue"] for i in issues)


class TestSegmentation:
    """Claims must land on the product they describe."""

    def test_claims_attach_to_the_nearest_preceding_product(self):
        draft = (
            "**Lenovo IdeaPad Slim 3 — ₹59,990**\n"
            "Has 9 hours of battery.\n\n"
            "**ASUS TUF Gaming A15 — ₹67,990**\n"
            "Has 8 hours of battery."
        )
        assert verify_grounding(draft, [LAPTOP_06, LAPTOP_08]) == []

    def test_swapping_the_two_battery_figures_is_caught_twice(self):
        draft = (
            "**Lenovo IdeaPad Slim 3 — ₹59,990**\n"
            "Has 8 hours of battery.\n\n"
            "**ASUS TUF Gaming A15 — ₹67,990**\n"
            "Has 9 hours of battery."
        )
        issues = verify_grounding(draft, [LAPTOP_06, LAPTOP_08])
        names = {i["product"] for i in issues if "battery" in i["issue"]}
        assert names == {LAPTOP_06["name"], LAPTOP_08["name"]}, (
            f"expected both products flagged, got: {_issue_text(issues)}"
        )

    def test_abbreviated_product_name_is_matched(self):
        """'HP 15s' must anchor to 'HP Laptop 15s-ey4002AU'."""
        draft = "**HP 15s — ₹64,999**\nFast CPU, 16GB RAM, 10 hours battery."
        assert verify_grounding(draft, [LAPTOP_07]) == []

    def test_abbreviated_name_still_catches_a_bad_claim(self):
        draft = "**HP 15s — ₹64,999**\nFast CPU, 16GB RAM, 14 hours battery."
        issues = verify_grounding(draft, [LAPTOP_07])
        assert any("battery mismatch" in i["issue"] for i in issues)


class TestEdgeCases:

    def test_empty_draft_returns_empty(self):
        assert verify_grounding("", G01_PRODUCTS) == []

    def test_no_products_returns_empty_for_plain_text(self):
        assert verify_grounding("No matches found for that budget.", []) == []

    def test_no_products_still_catches_an_invented_id(self):
        issues = verify_grounding("Try laptop_01 instead.", [])
        assert any("laptop_01" in i["claim"] for i in issues)

    def test_response_with_no_product_mention_returns_empty(self):
        draft = "Nothing in the catalog fits both constraints at that budget."
        assert verify_grounding(draft, G01_PRODUCTS) == []

    def test_issue_dicts_have_the_documented_shape(self):
        issues = verify_grounding(
            "**Sennheiser HD 206 — ₹1,490**\nGets 12 hours of battery.",
            [HP_02],
        )
        assert issues
        for issue in issues:
            assert set(issue) == {"product", "claim", "issue"}
            assert isinstance(issue["claim"], str) and issue["claim"]
            assert isinstance(issue["issue"], str) and issue["issue"]

    def test_gb_claim_on_headphones_has_no_field_to_match(self):
        draft = "**Sennheiser HD 206 — ₹1,490**\nComes with 512GB of storage."
        issues = verify_grounding(draft, [HP_02])
        assert any("neither ram_gb nor storage_gb" in i["issue"] for i in issues)

    def test_storage_and_ram_are_distinguished(self):
        """512GB SSD and 16GB RAM must each match their own field."""
        draft = "**HP 15s — ₹64,999**\n16GB RAM and a 512GB SSD."
        assert verify_grounding(draft, [LAPTOP_07]) == []

    def test_storage_figure_swapped_with_ram_is_caught(self):
        draft = "**HP 15s — ₹64,999**\n512GB RAM and a 16GB SSD."
        issues = verify_grounding(draft, [LAPTOP_07])
        kinds = {i["issue"].split(":")[0] for i in issues}
        assert "RAM mismatch" in kinds and "storage mismatch" in kinds, (
            f"expected both flagged: {_issue_text(issues)}"
        )


# ---------------------------------------------------------------------------
# Regressions from the first live run of the gate
# ---------------------------------------------------------------------------

BOAT_141 = {
    "id": "headphones_15",
    "name": "boAt Airdopes 141 (True Wireless, 8mm, BT 5.1, Passive Isolation, 6hr buds+36hr case)",
    "category": "headphones", "price": 999, "avg_rating": 4.0,
    "review_count": 180000, "warranty_months": 12,
    "connectivity_type": "true_wireless", "noise_cancellation": "passive",
    "codec_support": "SBC", "driver_size_mm": 8, "battery_hours": 6,
    "audio_score": 5.13,
}


class TestLiveRunFalsePositives:
    """Every one of these fired on a CORRECT draft in the first live run.

    A grounding gate that flags accurate responses gets switched off, so
    each is pinned here. The paired true-positive test in each case confirms
    the fix narrowed the check rather than disabling it.
    """

    def test_bare_ram_figure_followed_by_storage(self):
        """'16GB, 512GB SSD' — the SSD belongs to the NEXT spec, not the 16GB."""
        draft = (
            "**ASUS VivoBook 15 X1504ZA — ₹57,990**\n"
            "Core i5-1235U with 16GB, 512GB SSD and an OLED panel."
        )
        assert verify_grounding(draft, [LAPTOP_05]) == []

    def test_wrong_ram_in_the_same_shape_still_fires(self):
        draft = (
            "**ASUS VivoBook 15 X1504ZA — ₹57,990**\n"
            "Core i5-1235U with 32GB, 512GB SSD and an OLED panel."
        )
        assert verify_grounding(draft, [LAPTOP_05]) != []

    def test_budget_restated_in_the_preamble(self):
        """'Here's what fits under ₹5,000:' is the user's budget, not a price."""
        draft = (
            "Here's what fits under ₹5,000:\n\n"
            "**Samsung Galaxy Buds FE — ₹3,999**\nSolid ANC for the money."
        )
        assert verify_grounding(draft, [HP_16]) == []

    def test_budget_restated_inside_a_segment(self):
        draft = (
            "**JBL Tune 500 — ₹999**\nComes in well under your ₹1,500 budget."
        )
        assert verify_grounding(draft, [HP_06]) == []

    def test_wrong_price_still_fires_after_the_budget_fix(self):
        draft = "**JBL Tune 500 — ₹1,299**\nThat's the price."
        issues = verify_grounding(draft, [HP_06])
        assert any("price mismatch" in i["issue"] for i in issues)

    @pytest.mark.parametrize("product,draft", [
        (HP_16, "**Samsung Galaxy Buds FE — ₹3,999**\n"
                "6 hours on the buds, 21 hours total with the case."),
        (BOAT_141, "**boAt Airdopes 141 — ₹999**\n"
                   "6 hours per charge, 36 hours with the case."),
    ])
    def test_case_battery_figure_from_the_product_name(self, product, draft):
        """battery_hours is 6, but the name records the case total too.

        The draft is accurate; matching against battery_hours alone made it
        look like a hallucination. See _value_in_name.
        """
        assert verify_grounding(draft, [product]) == []

    def test_invented_battery_figure_not_in_the_name_still_fires(self):
        """30 appears in neither battery_hours nor the name."""
        draft = "**Samsung Galaxy Buds FE — ₹3,999**\n30 hours of battery."
        issues = verify_grounding(draft, [HP_16])
        assert any("battery mismatch" in i["issue"] for i in issues)

    def test_name_fallback_does_not_apply_to_gpu(self):
        """gpu_model stays authoritative even though the name prints the code.

        laptop_08's name contains "RTX 3050"; a draft claiming RTX 4060 must
        still fail, and the null-gpu case must not be rescued by the name.
        """
        draft = "**ASUS TUF Gaming A15 — ₹67,990**\nHas an RTX 4060."
        assert verify_grounding(draft, [LAPTOP_08]) != []


class TestClosingSummaryAttribution:
    """Regression from the second live run.

    A closing paragraph shortens a name already introduced in full ("take
    the HD 206"). If only the leading tokens anchor, that sentence stays in
    the PREVIOUS product's segment and its price is checked against the
    wrong product — which reported the Sennheiser's real ₹1,490 as a JBL
    mismatch.
    """

    SUMMARY_DRAFT = (
        "**1. Sennheiser HD 206 — ₹1,490**\n"
        "The best-sounding pick here, 36mm drivers.\n\n"
        "**2. Sony MDR-ZX310AP — ₹1,390**\n"
        "Close second on audio, 30mm drivers.\n\n"
        "**3. JBL Tune 500 — ₹999**\n"
        "Behind the other two on audio, but it's ₹500 cheaper.\n\n"
        "**My call:** the HD 206. You've got ₹1,500 to spend and it's the "
        "clear sound-quality leader at ₹1,490 — no reason to save ₹100."
    )

    def test_no_false_positive(self):
        assert verify_grounding(self.SUMMARY_DRAFT, G19_PRODUCTS) == []

    def test_summary_anchors_to_the_product_it_names(self):
        from agent.verify_grounding import _segment
        _pre, segments, _iss = _segment(self.SUMMARY_DRAFT, G19_PRODUCTS)
        assert segments[-1][0]["id"] == "headphones_02", (
            "the closing paragraph should belong to the Sennheiser it names, "
            f"not {segments[-1][0]['id']}"
        )

    def test_shortened_form_must_be_unique_to_anchor(self):
        """Two identically-named entries share every run, so neither wins.

        Both catalog "Lenovo IdeaPad Slim 3" rows produce the same token
        runs; the ambiguity path must handle it rather than a shortened form
        silently picking one.
        """
        twin = dict(LAPTOP_06, id="laptop_02", price=44990, battery_hours=7)
        draft = "**Lenovo IdeaPad Slim 3 — ₹59,990**\nGets 9 hours."
        issues = verify_grounding(draft, [LAPTOP_06, twin])
        assert all("mismatch" not in i["issue"] for i in issues), (
            f"price/battery wrongly attributed: {_issue_text(issues)}"
        )

    def test_swapped_prices_are_still_caught(self):
        """The anchor fix must not blunt real misattribution detection."""
        swapped = (
            "**1. Sennheiser HD 206 — ₹1,390**\nBest sounding.\n\n"
            "**2. Sony MDR-ZX310AP — ₹1,490**\nClose second."
        )
        issues = verify_grounding(swapped, G19_PRODUCTS)
        flagged = {i["product"] for i in issues if "price mismatch" in i["issue"]}
        assert flagged == {HP_02["name"], HP_05["name"]}, (
            f"expected both products flagged: {_issue_text(issues)}"
        )


class TestComparativeDeltaPhrasings:
    """Phrasings from the live runs that name a difference, not a price."""

    @pytest.mark.parametrize("sentence", [
        "The real question is whether ANC is worth ₹3,000 to you.",
        "You've got ₹1,500 to spend.",
        "It's ₹3,000 cheaper than the Samsung.",
        "Whether the build quality justifies ₹3,000.",
        "That leaves you ₹500 to play with.",
    ])
    def test_not_read_as_a_price_claim(self, sentence):
        draft = f"**JBL Tune 500 — ₹999**\n{sentence}"
        issues = verify_grounding(draft, [HP_06])
        assert issues == [], f"delta read as price: {_issue_text(issues)}"

    @pytest.mark.parametrize("sentence", [
        "It's the pick only if you'd rather bank ₹500.",
        "You pocket ₹500 going this route.",
        "You keep ₹500 in your pocket.",
    ])
    def test_money_verb_synonyms_for_saving(self, sentence):
        """Third live run surfaced 'bank ₹500'; same family as 'save'."""
        draft = f"**JBL Tune 500 — ₹999**\n{sentence}"
        assert verify_grounding(draft, [HP_06]) == []
