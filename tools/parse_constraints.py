# -*- coding: utf-8 -*-
"""
tools/parse_constraints.py
--------------------------
Rule-based NLP parser that extracts structured shopping constraints from a
user's natural-language message.

Deliberately avoids LLM calls so that it is:
  • Deterministic and fast (no network latency)
  • Fully unit-testable with exact expected outputs
  • Safe to call in any context (no API keys required)

The function relies on carefully ordered regex patterns and explicit signal
lists so that the "priority" field is ONLY set when the user makes a clear,
direct statement — never inferred from use-case alone.

Output schema
-------------
{
  "category"                      : "laptop" | "phone" | "headphones" | None,
  "connectivity_type"             : "wired" | "wireless" | "true_wireless" | None,
  "budget"                        : float | None,      # = budget_max when range detected
  "budget_min"                    : float | None,      # only set when a range is detected
  "budget_max"                    : float | None,      # only set when a range is detected
  "use_case"                      : str | None,
  "priority"                      : str | None,        # only if EXPLICITLY stated
  "ambiguous_signals"             : list[dict],        # [{"type": "budget"|"priority", "term": str}]
  "detected_out_of_catalog_product": str | None,       # named product not in catalog, or None
}
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
Constraints = dict[str, Any]


# ---------------------------------------------------------------------------
# Category signals
# ---------------------------------------------------------------------------

_LAPTOP_SIGNALS = [
    r'\blaptop\b', r'\bnotebook\b', r'\bmacbook\b', r'\bchromebook\b',
    r'\bultrabook\b', r'\bwindows\s+(?:pc|computer)\b',
]

_PHONE_SIGNALS = [
    r'\bphone\b', r'\bsmartphone\b', r'\bmobile\b',
    r'\biphone\b', r'\bandroid\b',
    r'\bpixel\b',  # Google Pixel line
]

_HEADPHONES_SIGNALS = [
    r'\bheadphones?\b', r'\bearphones?\b', r'\bearbuds?\b',
    r'\bheadset\b', r'\btwse?\b', r'\bin[- ]ears?\b',
    r'\bover[- ]ears?\b', r'\bon[- ]ears?\b',
    r'\bnoise[- ]cancell?ing\b', r'\banc\b',
    r'\bwireless\s+buds\b',
]


# ---------------------------------------------------------------------------
# Out-of-catalog product keywords
#
# Common electronics the user might ask for that are NOT in this catalog.
# Each entry is (keyword_regex, canonical_term).  The canonical term is what
# gets stored in detected_out_of_catalog_product.
#
# Checked ONLY when _detect_category() returns None, so a real category match
# (e.g. "laptop") always wins and is never mis-flagged as unsupported.
# ---------------------------------------------------------------------------

_OUT_OF_CATALOG_KEYWORDS: list[tuple[str, str]] = [
    (r'\bmics?\b',                    'mic'),
    (r'\bmicrophones?\b',             'microphone'),
    (r'\bwebcams?\b',                 'webcam'),
    (r'\bkeyboards?\b',              'keyboard'),
    (r'\bmouses?\b|\bmice\b',        'mouse'),
    (r'\bmonitors?\b',               'monitor'),
    (r'\bspeakers?\b',               'speaker'),
    (r'\bsmartwatches?\b',           'smartwatch'),
    (r'\btablets?\b',                'tablet'),
    (r'\bcameras?\b',                'camera'),
    (r'\bdesktops?\b|\b(?:gaming\s+)?pc\b|\btower\s+(?:pc|computer)\b', 'desktop'),
    (r'\bgaming\s+console\b|\bconsoles?\b', 'gaming console'),
    (r'\btelevisions?\b|\b(?:smart\s+)?tv\b', 'TV'),
    (r'\brouters?\b',                'router'),
    (r'\bprinters?\b',               'printer'),
    (r'\bpower\s+banks?\b',          'power bank'),
    # Note: 'charger' and 'cable' are intentionally omitted — they appear
    # frequently as accessory descriptors in legitimate headphone/device queries
    # (e.g. "earphones with an aux cable") and would produce false positives.
]


def _detect_out_of_catalog(text: str) -> str | None:
    """Return the canonical name of a known-unsupported product if found, else None.

    Only call this AFTER _detect_category() has returned None — if a real
    supported category was detected, that match should win unconditionally.
    """
    for pattern, canonical in _OUT_OF_CATALOG_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return canonical
    return None


# ---------------------------------------------------------------------------
# Connectivity signals (headphones only)
# ---------------------------------------------------------------------------

# true_wireless must be checked BEFORE wireless (it's more specific)
_TRUE_WIRELESS_SIGNALS = [
    r'\btrue[\s-]wireless\b', r'\btws\b', r'\bearbuds?\b',
    r'\bfully[\s-]wireless\b',
]

_WIRELESS_SIGNALS = [
    r'\bbluetooth\b', r'\bbt\b', r'\bwireless\b',
]

_WIRED_SIGNALS = [
    r'\bwired\b', r'\b3\.5\s*mm\b', r'\baux\b', r'\bjack\b',
    r'\bcable\b', r'\bplugged?\s+in\b',
]


# ---------------------------------------------------------------------------
# Priority signals
#
# These are EXPLICIT user statements only.  Use-case words (e.g. "gaming",
# "video editing") deliberately do NOT appear here — the orchestrator is
# responsible for asking a clarifying question when priority is ambiguous.
# ---------------------------------------------------------------------------

_PRIORITY_PATTERNS: list[tuple[str, list[str]]] = [
    ("performance", [
        r'\bbest\s+(?:processor|performance|cpu|gpu|speed)\b',
        r'\bmost\s+powerful\b',
        r'\bfastest\b',
        r'\bhigh(?:est)?\s+performance\b',
        r'\bperformance\s+(?:is|matters?|first|priority)\b',
        r'\bperformance\s+over\b',
        r'\bi\s+(?:care|want)\s+(?:most\s+)?about\s+performance\b',
        r'\bpowerful\s+(?:processor|chip|machine)\b',
        # Inverted phrasing — "priority is performance", "prioritise speed"
        r'\b(?:priority|focus)\s*(?:is|:|=)\s*(?:on\s+)?performance\b',
        r'\bprioriti[sz]e\s+(?:performance|speed)\b',
    ]),
    ("battery", [
        r'\bbattery\s+(?:life\s+)?(?:is|matters?|first|priority|most\s+important)\b',
        r'\bbattery\s+matters?\b',
        r'\blong(?:est)?\s+battery\b',
        r'\blong\s+battery\s+life\b',
        r'\bmaximum\s+battery\b',
        r'\bbest\s+battery\b',
        r'\bi\s+(?:care|want)\s+(?:most\s+)?about\s+battery\b',
        r'\bbattery\s+is\s+(?:key|critical|the\s+priority|top\s+priority)\b',
        # Category 1 fix — "-wise" and "last…workday" phrasing
        r'\bbattery[-\s]wise\b',
        r'\bneed(?:s)?\s+(?:it\s+)?to\s+last\b.{0,40}?\bbattery\b',
        r'\bbattery\s+(?:life\s+)?to\s+last\b',
        # Inverted phrasing — "priority is battery life", "prioritise battery"
        r'\b(?:priority|focus)\s*(?:is|:|=)\s*(?:on\s+)?battery\b',
        r'\bprioriti[sz]e\s+battery\b',
    ]),
    ("value", [
        r'\bvalue\s+for\s+(?:my\s+)?money\b',
        r'\bbest\s+value\b',
        r'\bcheapest\s+(?:option|one|possible)?\b',
        r'\bmost\s+affordable\b',
        r'\bbest\s+(?:bang|deal)\b',
        r'\bbudget[\s-]friendly\b',
        r'\blow(?:est)?\s+(?:price|cost)\b',
        r'\bi\s+(?:care|want)\s+(?:most\s+)?about\s+(?:price|value|cost)\b',
        r'\bprice\s+(?:is|matters?|first|priority)\b',
        r'\bsave\s+(?:money|as\s+much\s+as\s+possible)\b',
        # Inverted phrasing — "priority is value", "prioritise price"
        r'\b(?:priority|focus)\s*(?:is|:|=)\s*(?:on\s+)?(?:value|price|cost)\b',
        r'\bprioriti[sz]e\s+(?:value|price|cost)\b',
    ]),
    ("sound_quality", [
        r'\bbest\s+(?:sound|audio)\b',
        r'\bsound\s+(?:quality\s+)?(?:is|matters?|first|priority)\b',
        r'\baudio\s+(?:quality\s+)?(?:is|matters?|first|priority)\b',
        r'\bhighest\s+(?:quality\s+)?(?:sound|audio)\b',
        r'\bpure\s+(?:sound|audio)\b',
        r'\bi\s+(?:care|want)\s+(?:most\s+)?about\s+(?:sound|audio)\b',
        r'\bsound\s+over\b',
        # Inverted phrasing — "priority is sound quality", "prioritise audio"
        r'\b(?:priority|focus)\s*(?:is|:|=)\s*(?:on\s+)?(?:sound|audio)\b',
        r'\bprioriti[sz]e\s+(?:sound|audio)\b',
    ]),
    ("balanced", [
        r'\bbalanced\b',
        r'\ball[\s-]around\b',
        r'\bwell[\s-]rounded\b',
        r'\bno\s+specific\s+priority\b',
        r'\bequally\b',
        r'\bevery(?:thing)?\s+equally\b',
    ]),
]

# Use-case phrases that should NOT trigger priority inference —
# documentation only; not used in active code.
_NON_PRIORITY_USE_CASES = [
    "gaming", "video editing", "coding", "programming", "office work",
    "music", "calls", "watching videos", "streaming", "travel",
]


# ---------------------------------------------------------------------------
# Ambiguous signal detection (Category 2)
#
# These are SUBJECTIVE / RELATIVE terms.  The parser surfaces them so that
# the orchestrator can decide what to do (ask a clarifying question, etc.)
# but does NOT attempt to resolve them into a number or priority value.
#
# Lists are sorted longest-pattern-first so that "nothing crazy expensive"
# is matched before the shorter "expensive" in the same string.
# ---------------------------------------------------------------------------

_BUDGET_AMBIGUOUS_SIGNALS: list[tuple[str, str]] = sorted([
    (r'\bnothing\s+crazy\s+expensive\b',  'nothing crazy expensive'),
    (r'\bnot\s+too\s+costly\b',           'not too costly'),
    (r'\bbudget[-\s]friendly\b',          'budget-friendly'),
    (r'\binexpensive\b',                  'inexpensive'),
    (r'\baffordable\b',                   'affordable'),
    (r'\breasonable\b',                   'reasonable'),
    (r'\bexpensive\b',                    'expensive'),
    (r'\bpricey\b',                       'pricey'),
    (r'\bpremium\b',                      'premium'),
    (r'\bcheap\b',                        'cheap'),
], key=lambda x: len(x[0]), reverse=True)

_PRIORITY_AMBIGUOUS_SIGNALS: list[tuple[str, str]] = sorted([
    (r"\bdon'?t\s+care\s+about\s+(?:anything\s+)?fancy\b", 'nothing fancy'),
    (r'\bnothing\s+fancy\b',              'nothing fancy'),
    (r'\bhigh\s+quality\b',               'high quality'),
    (r'\bgood\s+quality\b',               'good quality'),
    (r'\bgreat\s+sound\b',                'great sound'),
    (r'\btop[-\s]notch\b',                'top-notch'),
    (r'\bthe\s+best\b',                   'the best'),
    (r'\bdecent\b',                       'decent'),
], key=lambda x: len(x[0]), reverse=True)


# ---------------------------------------------------------------------------
# Use-case extraction
# ---------------------------------------------------------------------------

_USE_CASE_PATTERNS = [
    r'(?:for|to\s+(?:do|use\s+for)|used?\s+(?:for|mainly|primarily))\s+([a-z][a-z\s,/&-]{2,40}?)(?:\.|,|$|\band\b|\bwith\b)',
    r'(?:mostly|mainly|primarily)\s+(?:for\s+)?([a-z][a-z\s,/&-]{2,40}?)(?:\.|,|$|\band\b)',
    r'(?:my\s+(?:primary\s+)?use\s+(?:case|is|for|will\s+be))\s+(?:is\s+)?([a-z][a-z\s,/&-]{2,40}?)(?:\.|,|$)',
]

# Words that should not appear at START of a captured use-case (likely noise)
_USE_CASE_BLACKLIST_START = re.compile(
    r'^(?:a|an|the|some|any|my|me|i|it|this|that|these|those|one|good|great|best)\b',
    re.IGNORECASE
)

# Maximum use-case length (characters)
_USE_CASE_MAX_LEN = 60


# ---------------------------------------------------------------------------
# Word-form number maps (Category 1 fix)
# ---------------------------------------------------------------------------

_ONES_MAP: dict[str, int] = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
    'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
    'nineteen': 19,
}
_TENS_MAP: dict[str, int] = {
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
}


# ---------------------------------------------------------------------------
# Budget extraction
# ---------------------------------------------------------------------------

def _parse_word_number_budget(text: str) -> float | None:
    """Parse word-form numbers followed by a multiplier.

    Examples: "sixty thousand" → 60000, "fifteen thousand" → 15000,
              "twenty five thousand" → 25000, "two lakh" → 200000
    """
    t = text.lower()
    tens_pat = '|'.join(_TENS_MAP.keys())
    # Longest-first so "thirteen" beats "three", "fourteen" beats "four", etc.
    ones_pat = '|'.join(sorted(_ONES_MAP.keys(), key=len, reverse=True))
    mult_grp = r'(thousand|lakh|lac)'

    # Pattern A: [tens] ones multiplier  — "twenty five thousand", "fifteen thousand"
    pat_a = (
        r'\b(?:(' + tens_pat + r')[-\s]+)?'
        r'(' + ones_pat + r')\s+'
        + mult_grp + r'\b'
    )
    m = re.search(pat_a, t, re.IGNORECASE)
    if m:
        tens_val = _TENS_MAP.get((m.group(1) or '').lower(), 0)
        ones_val = _ONES_MAP.get(m.group(2).lower(), 0)
        value = tens_val + ones_val
        if value > 0:
            mult_w = m.group(3).lower()
            mult = 100_000 if mult_w in ('lakh', 'lac') else 1_000
            return float(value * mult)

    # Pattern B: tens multiplier only — "sixty thousand", "fifty lakh"
    pat_b = r'\b(' + tens_pat + r')\s+' + mult_grp + r'\b'
    m = re.search(pat_b, t, re.IGNORECASE)
    if m:
        tens_val = _TENS_MAP.get(m.group(1).lower(), 0)
        if tens_val > 0:
            mult_w = m.group(2).lower()
            mult = 100_000 if mult_w in ('lakh', 'lac') else 1_000
            return float(tens_val * mult)

    return None


def _parse_range_budget(text: str) -> tuple[float, float] | None:
    """Detect an explicit price range and return (min, max).

    Handles: "50-60k", "50k-60k", "30k-50k", "50k to 60k", "between 40k and 80k"
    Returns None for single values or non-price ranges.
    """
    t = text.lower()

    def _process_range_values(raw1: float, k1: str, raw2: float, k2: str) -> tuple[float, float] | None:
        has_k1 = k1.lower() == 'k'
        has_k2 = k2.lower() == 'k'
        
        # Calculate v1
        if has_k1:
            v1 = raw1 * 1000.0
        elif has_k2:
            v1 = raw1 * 1000.0 if raw1 < 1000.0 else raw1
        else:
            v1 = raw1

        # Calculate v2
        if has_k2:
            v2 = raw2 * 1000.0
        elif has_k1:
            v2 = raw2 * 1000.0 if raw2 < 1000.0 else raw2
        else:
            v2 = raw2

        # If neither side has 'k', we only treat it as a budget range if both are >= 100
        if not has_k1 and not has_k2:
            if v1 < 100.0 or v2 < 100.0:
                return None

        return (min(v1, v2), max(v1, v2))

    # Hyphen/dash range: NUM(k?) – NUM(k?)
    m = re.search(
        r'(?<!\d)(\d+(?:\.\d+)?)\s*(k?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(k?)\b',
        t, re.IGNORECASE
    )
    if m:
        raw1, k1 = float(m.group(1)), m.group(2).lower()
        raw2, k2 = float(m.group(3)), m.group(4).lower()
        res = _process_range_values(raw1, k1, raw2, k2)
        if res is not None:
            return res

    # "to"/"and" range: NUM(k?) to/and NUM(k?)
    m = re.search(
        r'(?<!\d)(\d+(?:\.\d+)?)\s*(k?)\s+(?:to|and)\s+(\d+(?:\.\d+)?)\s*(k?)\b',
        t, re.IGNORECASE
    )
    if m:
        raw1, k1 = float(m.group(1)), m.group(2).lower()
        raw2, k2 = float(m.group(3)), m.group(4).lower()
        res = _process_range_values(raw1, k1, raw2, k2)
        if res is not None:
            return res

    return None


def _parse_budget(text: str) -> float | None:
    """Extract a single numeric budget from the message.  Returns None if absent.

    Extraction order (stops at first match):
      1. Digit + lakh              — "1.5 lakh"
      2. Word-form number          — "sixty thousand", "fifteen thousand"
      3. Digit + thousand word     — "10 thousand", "under 10 thousand rupees"
      4. k-suffix                  — "60k", "60K"
      5. Keyword-anchored number   — "under 15000", "Rs. 60,000", "budget of 50k"
      6. Bare currency symbol      — "₹60,000"
      7. Bare large integer        — "15000" (≥4 digits, not a year)
    """
    t = text.strip()

    # 1. Digit + lakh / lac
    m = re.search(r'(?<!\w)(\d+(?:\.\d+)?)\s*(?:lakh|lac)s?\b', t, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 100_000

    # 2. Word-form numbers ("sixty thousand", "fifteen thousand")
    val = _parse_word_number_budget(t)
    if val is not None:
        return val

    # 3. Digit + "thousand" word — checked BEFORE keyword-anchored so that
    #    "under 10 thousand rupees" returns 10000, not 10.
    m = re.search(r'(?<!\w)(\d+(?:\.\d+)?)\s+thousand\b', t, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 1_000

    # 4. k-suffix  — "60k", "60K", "7.5k"
    m = re.search(r'(?<!\w)(\d+(?:\.\d+)?)\s*k(?!\w)', t, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 1_000

    # 5. Keyword-anchored number  — "under 15000", "Rs. 60,000", "budget of 50,000"
    m = re.search(
        r'(?:'
        r'under|below|less\s+than|within|up\s+to|around|about|approximately'
        r'|max(?:imum)?|rs\.?|rupees?'
        r'|budget\s*(?:of|is|around|:)?'
        r'|my\s+budget\s+(?:is|was|would\s+be)?'
        r')\s*[₹$]?\s*(\d[\d,]*(?:\.\d+)?)',
        t, re.IGNORECASE
    )
    if m:
        return float(m.group(1).replace(',', ''))

    # 6. Bare currency symbol  — "₹60,000"
    m = re.search(r'[₹$]\s*(\d[\d,]*(?:\.\d+)?)', t)
    if m:
        return float(m.group(1).replace(',', ''))

    # 7. Bare large integer (≥4 digits) that isn't obviously a year (1900–2099)
    for m in re.finditer(r'\b(\d{4,}(?:,\d+)*)\b', t):
        val = float(m.group(1).replace(',', ''))
        if 1900 <= val <= 2099:
            continue
        return val

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_any(patterns: list[str], text: str) -> bool:
    """Return True if ANY of the regex patterns matches (case-insensitive)."""
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _detect_category(text: str) -> str | None:
    """Return the product category, or None.

    Headphones are checked FIRST because their signals are unambiguous
    product nouns, while laptop/phone words are frequently just the host
    device the headphones plug into ("mobile headphones", "earbuds for my
    laptop").  Checking laptop or phone first made the qualifier win over
    the product actually being bought.
    """
    if _match_any(_HEADPHONES_SIGNALS, text):
        return "headphones"
    if _match_any(_LAPTOP_SIGNALS, text):
        return "laptop"
    if _match_any(_PHONE_SIGNALS, text):
        return "phone"
    return None


def _detect_connectivity(text: str) -> str | None:
    """Detect connectivity type.

    Priority order:
      1. wired  — explicit, unambiguous signals checked FIRST so that a
                  negated wireless term ("I don't like Bluetooth") doesn't
                  override an explicit "wired" or "3.5mm" mention.
      2. true_wireless — more specific than plain wireless.
      3. wireless — broadest match, checked last.
    """
    if _match_any(_WIRED_SIGNALS, text):
        return "wired"
    if _match_any(_TRUE_WIRELESS_SIGNALS, text):
        return "true_wireless"
    if _match_any(_WIRELESS_SIGNALS, text):
        return "wireless"
    return None


def _detect_priority(text: str) -> str | None:
    """Return the EXPLICITLY stated priority, or None.

    Matches the highest-scoring priority category.  A priority is only
    returned when the user makes a direct statement — use-case words alone
    (e.g. "gaming") never trigger this.
    """
    best_priority = None
    best_count = 0

    for priority_name, patterns in _PRIORITY_PATTERNS:
        count = sum(
            1 for p in patterns if re.search(p, text, re.IGNORECASE)
        )
        if count > best_count:
            best_count = count
            best_priority = priority_name

    return best_priority if best_count > 0 else None


def _detect_use_case(text: str) -> str | None:
    """Extract a short free-text use-case description."""
    t = text.lower()
    for pattern in _USE_CASE_PATTERNS:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().rstrip('.,;')
            if _USE_CASE_BLACKLIST_START.match(candidate):
                continue
            if len(candidate) < 3 or len(candidate) > _USE_CASE_MAX_LEN:
                continue
            return candidate
    return None


def _detect_ambiguous_signals(
    text: str,
    budget: float | None,
    priority: str | None,
) -> list[dict]:
    """Return a list of ambiguous/subjective signal objects.

    Only fires when the corresponding explicit field is NOT already set.
    At most one budget entry and one priority entry are returned.

    Each entry: {"type": "budget"|"priority", "term": "<exact term matched>"}
    """
    signals: list[dict] = []

    # Budget-ambiguous terms — only when no numeric budget was extracted
    if budget is None:
        for pat, term in _BUDGET_AMBIGUOUS_SIGNALS:
            if re.search(pat, text, re.IGNORECASE):
                signals.append({"type": "budget", "term": term})
                break  # one entry per type

    # Priority-ambiguous terms — only when no explicit priority was extracted
    if priority is None:
        for pat, term in _PRIORITY_AMBIGUOUS_SIGNALS:
            if re.search(pat, text, re.IGNORECASE):
                signals.append({"type": "priority", "term": term})
                break

    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_constraints(
    user_message: str,
    prior_context: Constraints | None = None,
) -> Constraints:
    """Extract structured shopping constraints from a natural-language message.

    Parameters
    ----------
    user_message : str
        The user's raw input string.
    prior_context : dict | None
        Optional dict of previously extracted constraints (from an earlier
        turn).  Any field that is ``None`` or an empty list in the current
        parse but present in ``prior_context`` will be carried forward.
        Fields extracted from the current message always win.

    Returns
    -------
    dict with keys:
        category                       – "laptop" | "phone" | "headphones" | None
        connectivity_type              – "wired" | "wireless" | "true_wireless" | None
        budget                         – float | None   (= budget_max when range detected)
        budget_min                     – float | None   (only set when a price range detected)
        budget_max                     – float | None   (only set when a price range detected)
        use_case                       – str | None
        priority                       – str | None     (only if EXPLICITLY stated)
        ambiguous_signals              – list[dict]     (subjective terms that need clarification)
        detected_out_of_catalog_product – str | None    (named product not carried in catalog)
    """
    _empty: Constraints = {
        "category": None,
        "connectivity_type": None,
        "budget": None,
        "budget_min": None,
        "budget_max": None,
        "use_case": None,
        "priority": None,
        "ambiguous_signals": [],
        "detected_out_of_catalog_product": None,
    }

    if not user_message or not user_message.strip():
        result = dict(_empty)
        if prior_context:
            for key in result:
                cur = result[key]
                prior_val = prior_context.get(key)
                if (cur is None or cur == []) and prior_val:
                    result[key] = prior_val
        return result

    msg = user_message.strip()

    # Out-of-catalog detection runs BEFORE category detection.
    # If the user has named a product we don't carry (e.g. "mic", "webcam"),
    # the subject of the purchase is clearly that unsupported item and any
    # incidental device mention ("windows pc", "my laptop") is just context
    # for what they'll plug it into — we must not mistake it for the thing
    # being bought.  So when an OOC product is detected, category stays None.
    out_of_catalog: str | None = _detect_out_of_catalog(msg)

    category = None if out_of_catalog else _detect_category(msg)

    # Connectivity is only meaningful for headphones, but the category may
    # have been established on an EARLIER turn — a reply of "true wireless"
    # carries no headphone noun of its own. Gating on the current message
    # alone silently discarded the answer to our own clarifying question.
    effective_category = category
    if effective_category is None and prior_context:
        effective_category = prior_context.get("category")

    connectivity_type = (
        _detect_connectivity(msg) if effective_category == "headphones" else None
    )

    # --- Budget: try range first, fall back to single value ---
    range_result = _parse_range_budget(msg)
    if range_result:
        budget_min, budget_max = range_result
        budget = budget_max         # backward-compat single value = upper bound
    else:
        budget_min = budget_max = None
        budget = _parse_budget(msg)

    use_case  = _detect_use_case(msg)
    priority  = _detect_priority(msg)

    # Don't expose connectivity_type when the category is unknown even after
    # consulting prior_context — it would have nothing to qualify.
    if effective_category is None:
        connectivity_type = None

    ambiguous_signals = _detect_ambiguous_signals(msg, budget, priority)

    result: Constraints = {
        "category":                       category,
        "connectivity_type":              connectivity_type,
        "budget":                         budget,
        "budget_min":                     budget_min,
        "budget_max":                     budget_max,
        "use_case":                       use_case,
        "priority":                       priority,
        "ambiguous_signals":              ambiguous_signals,
        "detected_out_of_catalog_product": out_of_catalog,
    }

    # Merge prior_context — current message always wins
    if prior_context:
        for key in result:
            cur = result[key]
            prior_val = prior_context.get(key)
            if (cur is None or cur == []) and prior_val:
                result[key] = prior_val

    return result
