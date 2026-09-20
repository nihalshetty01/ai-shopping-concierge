# -*- coding: utf-8 -*-
"""
agent/verify_grounding.py
-------------------------
Deterministic grounding check for draft concierge responses (PRD Section 10,
"Grounding check"; Eval Plan G11, G12, G22).

This is field-matching, NOT LLM self-grading. Every spec or price the draft
claims about a product is matched against that SPECIFIC product's field
value in the retrieved data. "Exists somewhere in the catalog" is not good
enough — claiming the ASUS TUF's GPU for the Lenovo is a grounding failure
even though both strings appear in the catalog.

Pipeline:
  STEP 1  Segment the draft by product mention.
  STEP 2  Structural check — a field that cannot exist for the product's
          category (battery on a wired headphone) is a violation regardless
          of the number attached.
  STEP 3  Claim extraction and per-product field matching.
  STEP 4  Return a list of issue dicts; an empty list means the draft passed.

Known limitations (deliberate, documented rather than hidden):
  • Claims in the preamble before the first product mention cannot be
    attributed to a product and are not checked at all.
  • Amounts written in shorthand ("₹1.4 lakh", "₹60k") are treated as
    conversational, not as price claims — see _price_claims.
  • Only the claim types the PRD enumerates are matched (price, RAM,
    storage, battery, GPU). Other prose specs carried in a product's `name`
    — Bluetooth version, driver size — are not verified.
  • A figure that appears verbatim with its unit in the product's own
    retrieved `name` is accepted even when the corresponding field says
    something else, because the name is retrieved data too. This is what
    lets a correct "21 hours with the case" pass when battery_hours is 6.
    The honest fix is to promote such specs to real fields, as gpu_model
    was; until then the name is the only record of them.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------
#
# Drafts almost never quote a catalog name verbatim. The catalog says
# "HP Laptop 15s-ey4002AU (AMD Ryzen 7 7730U, 16GB, 512GB SSD, 15.6 FHD)";
# a good response says "HP 15s". So an anchor is built from the name's
# distinctive tokens, requiring the first two in order, allowing a couple of
# filler words between tokens, and treating later tokens as optional (a
# longer match simply wins over a shorter one).

# Generic words that carry no identifying information.
_NAME_STOPWORDS = frozenset({"laptop", "notebook", "the", "with"})

# Up to two unrelated words may sit between two distinctive tokens.
_GAP = r"(?:\W+\S+){0,2}?\W+"


def _distinctive_tokens(name: str) -> list[str]:
    """Identifying tokens from a product name, in order.

    Only the part before the first parenthesis is used — the parenthetical
    is a spec list, not an identifier, and matching on it would let one
    product's anchor fire on another product's specs.
    """
    base = name.split("(")[0]
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9./-]*", base)
    return [t for t in tokens if t.lower() not in _NAME_STOPWORDS]


def _token_alternatives(token: str) -> str:
    """Regex alternation for one token, allowing a truncated model code.

    "15s-ey4002AU" also matches a draft that writes just "15s".
    """
    variants = {token}
    if "-" in token:
        head = token.split("-")[0]
        if head:
            variants.add(head)
    ordered = sorted(variants, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(v) for v in ordered) + ")"


def _run_regex(tokens: list[str]) -> re.Pattern:
    """Pattern requiring every token in this run, in order, with filler."""
    parts = [_token_alternatives(tokens[0])]
    for tok in tokens[1:]:
        parts.append(_GAP + _token_alternatives(tok))
    return re.compile(r"(?<![A-Za-z0-9])" + "".join(parts), re.IGNORECASE)


def _token_runs(tokens: list[str]) -> list[list[str]]:
    """Every contiguous run of two or more tokens, longest first.

    Two tokens minimum: a lone brand must not anchor, or "take the Lenovo"
    in a closing paragraph would claim the segment.
    """
    runs = []
    for length in range(len(tokens), 1, -1):
        for start in range(0, len(tokens) - length + 1):
            runs.append(tokens[start:start + length])
    return runs


def _anchor_patterns(product: dict, others: list[dict]) -> list[re.Pattern]:
    """Anchor patterns for one product, including unique shortened forms.

    A draft's closing paragraph routinely shortens a name it already
    introduced in full — "take the HD 206" for the Sennheiser HD 206. If
    only the leading tokens anchor, that sentence stays in the PREVIOUS
    product's segment and its price is checked against the wrong product.
    In the second live run that misattributed the Sennheiser's real ₹1,490
    to the JBL and reported it as a mismatch.

    So any contiguous run of the name's tokens is usable as an anchor,
    provided no other retrieved product contains that same run — that
    proviso is what keeps "IdeaPad Slim 3" from matching whichever of the
    two identically-named entries came first.
    """
    tokens = _distinctive_tokens(str(product.get("name", "")))
    if not tokens:
        return []

    other_tokens = [
        [t.lower() for t in _distinctive_tokens(str(o.get("name", "")))]
        for o in others
    ]

    def is_unique(run: list[str]) -> bool:
        lowered = [t.lower() for t in run]
        width = len(lowered)
        for other in other_tokens:
            for start in range(0, max(0, len(other) - width) + 1):
                if other[start:start + width] == lowered:
                    return False
        return True

    patterns = [_run_regex(tokens)] if len(tokens) >= 2 else []
    for run in _token_runs(tokens):
        if run != tokens and is_unique(run):
            patterns.append(_run_regex(run))

    if not patterns:
        patterns = [_run_regex(tokens)] if len(tokens) >= 2 else [
            _run_regex(tokens + tokens[:1])
        ]
    return patterns


# ---------------------------------------------------------------------------
# Claim patterns
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(
    r"₹\s?(\d[\d,]*(?:\.\d+)?)\s*(k|l|lakh|lakhs|cr|crore)?",
    re.IGNORECASE,
)

_GB_RE = re.compile(r"(\d+)\s?GB\b", re.IGNORECASE)
_BATTERY_RE = re.compile(r"(\d+)\s?(?:hours?|hrs?|hr)\b", re.IGNORECASE)
_GPU_RE = re.compile(r"\b(RTX|GTX)\s?(\d{4})\b", re.IGNORECASE)
_BATTERY_WORD_RE = re.compile(r"\bbatter(?:y|ies)\b", re.IGNORECASE)
_PRODUCT_ID_RE = re.compile(r"\b(?:laptop|phone|headphones)_\d+\b", re.IGNORECASE)

# A ₹ amount preceded or followed by one of these is commentary — a saving,
# a gap, a ceiling — not a claim about what the product costs.
_DELTA_BEFORE_RE = re.compile(
    r"\b(?:save[sd]?|saving|another|extra|additional|stretch|spare|"
    r"leftover|left|only|just|about|around|roughly|adds?|plus|below|"
    r"beyond|up\s+to|under|within|beneath|at\s+or\s+under|budget\s+of|"
    r"ceiling|cap|limit|spend|keep\s+it|worth|justif\w*|step\s+up\s+to|"
    r"got|bank|pocket|keep|hang\s+on\s+to|rather)\b[^.]{0,14}$",
    re.IGNORECASE,
)
_DELTA_AFTER_RE = re.compile(
    r"^[^.]{0,14}\b(?:more|less|over|under|cheaper|extra|apart|difference|"
    r"than|jump|gap|short|clear|budget|ceiling|cap|limit|mark|range|"
    r"or\s+under|or\s+less|to\s+spend|to\s+you|to\s+play\s+with)\b",
    re.IGNORECASE,
)

# Words that disambiguate a bare "16GB" between memory and storage.
_RAM_CONTEXT_RE = re.compile(r"\b(?:ram|memory)\b", re.IGNORECASE)
_STORAGE_CONTEXT_RE = re.compile(
    r"\b(?:ssd|hdd|storage|rom|emmc|nvme|drive|disk)\b", re.IGNORECASE
)


def _issue(product: str | None, claim: str, why: str) -> dict:
    return {"product": product, "claim": claim, "issue": why}


# Boundaries that end one spec and begin the next. Without cutting here, the
# context after a bare "16GB" in "16GB, 512GB SSD" reaches the FOLLOWING
# spec's "SSD" and the RAM figure gets matched against storage_gb.
_SPEC_BOUNDARIES = (",", ";", "\n", "+", " and ", " with ", " plus ", "/")


def _spec_context(segment: str, end: int, width: int = 26) -> str:
    """Text right after a figure, cut off before the next spec begins."""
    context = segment[end:end + width]
    for sep in _SPEC_BOUNDARIES:
        cut = context.find(sep)
        if cut != -1:
            context = context[:cut]
    following = _GB_RE.search(context)
    if following:
        context = context[:following.start()]
    return context


def _value_in_name(product: dict, value: int, unit_pattern: str) -> bool:
    """True if the figure appears with this unit in the product's own name.

    The retrieved `name` is retrieved data too, and it carries real specs
    that no field captures — "6hr Buds + 21hr Case" on a true-wireless
    entry, where battery_hours is only 6. A response citing the 21-hour
    case figure is accurate, so matching against battery_hours alone
    produced false positives on correct drafts.

    Deliberately NOT applied to GPU claims: gpu_model is authoritative
    there, and falling back to the name would let a null gpu_model pass on
    the strength of the model code printed in its own title.
    """
    name = str(product.get("name", ""))
    pattern = rf"(?<![\d.]){value}\s?(?:{unit_pattern})\b"
    return re.search(pattern, name, re.IGNORECASE) is not None


# ---------------------------------------------------------------------------
# STEP 1 — Segmentation
# ---------------------------------------------------------------------------

def _find_anchors(draft: str, products: list[dict]) -> tuple[list[tuple], list[dict]]:
    """Locate each product's mentions and return non-overlapping anchors.

    Returns (anchors, issues) where anchors is a list of
    (start, end, product) sorted by position.
    """
    issues: list[dict] = []
    candidates: list[tuple[int, int, dict]] = []

    for product in products:
        others = [o for o in products if o is not product]
        for rx in _anchor_patterns(product, others):
            for m in rx.finditer(draft):
                candidates.append((m.start(), m.end(), product))

    # Longest match at the earliest position wins.
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

    accepted: list[tuple[int, int, dict]] = []
    for start, end, product in candidates:
        if any(start < a_end and end > a_start for a_start, a_end, _ in accepted):
            continue

        # Two catalog entries can share a display name (there are two
        # "Lenovo IdeaPad Slim 3" and two "ASUS TUF Gaming A15" entries).
        # Price is the reliable discriminator when both are retrieved.
        tied = [
            c for c in candidates
            if c[0] == start and c[1] == end and c[2] is not product
        ]
        if tied:
            window = draft[start:start + 400]
            contenders = [product] + [c[2] for c in tied]
            priced = [
                p for p in contenders
                if _format_price_variants(p.get("price")) & _price_strings(window)
            ]
            if len(priced) == 1:
                product = priced[0]
            else:
                issues.append(_issue(
                    str(product.get("name")),
                    draft[start:end],
                    "ambiguous product reference — matches "
                    f"{len(contenders)} retrieved products "
                    f"({', '.join(str(p.get('id')) for p in contenders)}) "
                    "and no price disambiguates it",
                ))
        accepted.append((start, end, product))

    accepted.sort(key=lambda a: a[0])
    return accepted, issues


def _price_strings(text: str) -> set[str]:
    """Every ₹ amount in text, digits only."""
    return {m.group(1).replace(",", "") for m in _PRICE_RE.finditer(text)}


def _format_price_variants(price: Any) -> set[str]:
    if price is None:
        return set()
    return {str(int(price))}


def _segment(draft: str, products: list[dict]) -> tuple[str, list[tuple[dict, str]], list[dict]]:
    """Split the draft into (preamble, [(product, text), ...], issues)."""
    anchors, issues = _find_anchors(draft, products)
    if not anchors:
        return draft, [], issues

    preamble = draft[:anchors[0][0]]
    segments = []
    for i, (start, _end, product) in enumerate(anchors):
        stop = anchors[i + 1][0] if i + 1 < len(anchors) else len(draft)
        segments.append((product, draft[start:stop]))
    return preamble, segments, issues


# ---------------------------------------------------------------------------
# STEP 2 — Structural check
# ---------------------------------------------------------------------------

def _check_structural(product: dict, segment: str) -> list[dict]:
    """Flag fields that cannot exist for this product's category.

    A wired headphone has no battery at all (PRD 10.4), so the field is
    absent from the catalog entry rather than zero. Any mention of battery
    in its segment is unsupported by construction — this fires whether or
    not a number is attached, which is what separates it from a wrong value.
    """
    if product.get("connectivity_type") != "wired":
        return []

    match = _BATTERY_WORD_RE.search(segment)
    if not match:
        return []

    sentence = _containing_sentence(segment, match.start())
    return [_issue(
        str(product.get("name")),
        sentence,
        "structural violation: mentions battery for a wired headphone, a "
        "category with no battery_hours field at all (PRD 10.4)",
    )]


def _containing_sentence(text: str, index: int) -> str:
    """The sentence or line around index, for a readable claim quote."""
    start = max(
        text.rfind(".", 0, index),
        text.rfind("\n", 0, index),
        text.rfind("*", 0, index),
    )
    start = 0 if start < 0 else start + 1
    candidates = [p for p in (text.find(".", index), text.find("\n", index)) if p != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end].strip()


# ---------------------------------------------------------------------------
# STEP 3 — Claim extraction and matching
# ---------------------------------------------------------------------------

def _price_claims(segment: str) -> list[tuple[str, int]]:
    """(quoted text, value) for every ₹ amount that reads as a price claim.

    Shorthand amounts and amounts in delta contexts are excluded — a draft
    saying "(₹8k over)" or "save ₹500" is not claiming either number is the
    product's price, and flagging them would bury real errors in noise.
    """
    claims = []
    for m in _PRICE_RE.finditer(segment):
        digits, suffix = m.group(1), m.group(2)
        if suffix:
            continue
        plain = digits.replace(",", "")
        if not plain.isdigit() or len(plain) < 3:
            continue
        if _in_delta_context(segment, m.start(), m.end()):
            continue
        claims.append((m.group(0).strip(), int(plain)))
    return claims


def _in_delta_context(text: str, start: int, end: int) -> bool:
    """True if the amount is qualified as a difference rather than a price.

    Windows stop at the nearest ₹, bracket, or newline so that an adjacent
    parenthetical about a *different* amount cannot bleed in — without this,
    "₹64,999** (₹5k over)" would read "over" as qualifying ₹64,999.
    """
    before = text[max(0, start - 40):start]
    for sep in ("₹", "(", ")", "\n"):
        cut = before.rfind(sep)
        if cut != -1:
            before = before[cut + 1:]

    after = text[end:end + 40]
    for sep in ("₹", "(", ")", "\n"):
        cut = after.find(sep)
        if cut != -1:
            after = after[:cut]

    return bool(_DELTA_BEFORE_RE.search(before) or _DELTA_AFTER_RE.search(after))


def _check_price(product: dict, segment: str) -> list[dict]:
    issues = []
    actual = product.get("price")
    for quoted, value in _price_claims(segment):
        if actual is None:
            issues.append(_issue(str(product.get("name")), quoted,
                                 "price claimed but product has no price field"))
        elif value != int(actual):
            issues.append(_issue(
                str(product.get("name")), quoted,
                f"price mismatch: claims {value}, catalog says {int(actual)}",
            ))
    return issues


def _check_gb(product: dict, segment: str) -> list[dict]:
    """Match GB figures against ram_gb / storage_gb.

    A bare "16GB" is ambiguous, so it passes if it matches either field;
    only a figure matching neither is a mismatch.
    """
    issues = []
    ram, storage = product.get("ram_gb"), product.get("storage_gb")

    for m in _GB_RE.finditer(segment):
        value = int(m.group(1))
        quoted = m.group(0).strip()
        context = _spec_context(segment, m.end())

        if ram is None and storage is None:
            issues.append(_issue(
                str(product.get("name")), quoted,
                "capacity in GB claimed but this product category has "
                "neither ram_gb nor storage_gb",
            ))
            continue

        if _RAM_CONTEXT_RE.search(context):
            if ram is None:
                issues.append(_issue(str(product.get("name")), quoted,
                                     "RAM claimed but product has no ram_gb field"))
            elif value != int(ram):
                issues.append(_issue(
                    str(product.get("name")), quoted,
                    f"RAM mismatch: claims {value}GB, catalog says {int(ram)}GB",
                ))
        elif _STORAGE_CONTEXT_RE.search(context):
            if storage is None:
                issues.append(_issue(str(product.get("name")), quoted,
                                     "storage claimed but product has no storage_gb field"))
            elif value != int(storage):
                issues.append(_issue(
                    str(product.get("name")), quoted,
                    f"storage mismatch: claims {value}GB, catalog says {int(storage)}GB",
                ))
        else:
            allowed = {int(v) for v in (ram, storage) if v is not None}
            if value not in allowed and not _value_in_name(product, value, "GB"):
                issues.append(_issue(
                    str(product.get("name")), quoted,
                    f"{value}GB matches neither ram_gb "
                    f"({ram}) nor storage_gb ({storage})",
                ))
    return issues


def _check_battery(product: dict, segment: str) -> list[dict]:
    """Match hour figures against battery_hours.

    Wired headphones are skipped — _check_structural already reported the
    stronger structural finding, and a duplicate value mismatch would only
    dilute it.
    """
    if product.get("connectivity_type") == "wired":
        return []

    issues = []
    actual = product.get("battery_hours")
    for m in _BATTERY_RE.finditer(segment):
        value = int(m.group(1))
        quoted = m.group(0).strip()
        if actual is None:
            issues.append(_issue(
                str(product.get("name")), quoted,
                "battery life claimed but product has no battery_hours field",
            ))
        elif value != int(actual) and not _value_in_name(
            product, value, "hrs?|hours?|h"
        ):
            issues.append(_issue(
                str(product.get("name")), quoted,
                f"battery mismatch: claims {value} hours, catalog says "
                f"{int(actual)} hours",
            ))
    return issues


def _check_gpu(product: dict, segment: str) -> list[dict]:
    issues = []
    has_field = "gpu_model" in product
    actual = product.get("gpu_model")

    for m in _GPU_RE.finditer(segment):
        quoted = m.group(0).strip()
        claimed = f"{m.group(1).upper()} {m.group(2)}"

        if not has_field:
            issues.append(_issue(
                str(product.get("name")), quoted,
                "GPU claimed but this product category has no gpu_model field",
            ))
        elif actual is None:
            issues.append(_issue(
                str(product.get("name")), quoted,
                "claims a dedicated GPU but gpu_model is null "
                f"(graphics_type={product.get('graphics_type')!r})",
            ))
        elif claimed.lower() != str(actual).lower():
            issues.append(_issue(
                str(product.get("name")), quoted,
                f"GPU mismatch: claims {claimed}, catalog says {actual}",
            ))
    return issues


# ---------------------------------------------------------------------------
# Unknown product references
# ---------------------------------------------------------------------------

def _check_unknown_ids(draft: str, products: list[dict]) -> list[dict]:
    """Flag product ids that are not in the retrieved set (Eval Plan G12)."""
    known = {str(p.get("id", "")).lower() for p in products}
    issues = []
    for m in _PRODUCT_ID_RE.finditer(draft):
        found = m.group(0)
        if found.lower() not in known:
            issues.append(_issue(
                None, found,
                f"references product id {found!r}, which is not in the "
                "retrieved data",
            ))
    return issues


# NOTE — there is deliberately no preamble price check.
#
# An earlier version flagged any full-form price before the first product
# mention that matched no retrieved product. In a live run it fired on the
# most natural opening a concierge can write — "Here's what fits under
# ₹5,000:" — because the user's own stated budget is not any product's
# price. The check cost more in false positives than it earned, and a false
# positive on a correct response is how a grounding gate gets switched off.
# Preamble claims are therefore unverified; this is recorded in the module
# docstring's limitations.


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def verify_grounding(draft_response: str, retrieved_products: list[dict]) -> list[dict]:
    """Verify every claim in a draft response against the retrieved products.

    Parameters
    ----------
    draft_response : str
        The response text as drafted, before the user sees it.
    retrieved_products : list[dict]
        Exactly what ``catalog_search`` returned, with all real fields.

    Returns
    -------
    list[dict]
        One dict per issue — ``{"product", "claim", "issue"}`` — with
        ``product`` set to None when the claim cannot be attributed to a
        specific product. An empty list means the draft passed.
    """
    if not draft_response or not retrieved_products:
        return _check_unknown_ids(draft_response or "", retrieved_products or [])

    issues: list[dict] = []

    # Unknown references first — they are about the draft as a whole.
    issues.extend(_check_unknown_ids(draft_response, retrieved_products))

    _preamble, segments, segment_issues = _segment(draft_response, retrieved_products)
    issues.extend(segment_issues)

    for product, segment in segments:
        # STEP 2 always runs first: a structural violation is a stronger
        # finding than a wrong value and must not be masked by one.
        issues.extend(_check_structural(product, segment))
        # STEP 3
        issues.extend(_check_price(product, segment))
        issues.extend(_check_gb(product, segment))
        issues.extend(_check_battery(product, segment))
        issues.extend(_check_gpu(product, segment))

    return issues
