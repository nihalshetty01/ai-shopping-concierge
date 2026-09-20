# -*- coding: utf-8 -*-
"""
api/server.py
-------------
FastAPI backend server for the AI Shopping Concierge.

Exposes:
  • GET  /api/health          - Health check + Redis connectivity status.
  • GET  /api/products        - Full product catalog, optionally filtered by category.
  • GET  /api/products/{id}   - Single product by ID.
  • POST /api/chat            - Accepts user messages, manages stateful conversation
                            history sessions, and calls the agent Orchestrator.

Rate-limiting order in POST /api/chat:
  1. Load session state.
  2. Per-session cap check (SESSION_MAX_TURNS) — returns cap message immediately,
     never touches the daily counter.
  3. Daily cap check (read-only) — returns 429 if already at/over limit.
  4. Only if both checks pass: increment daily counter, then call Orchestrator.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# Load env variables (for ANTHROPIC_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Diagnostic startup logging: check Upstash Redis environment variables
_redis_url_check = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
_redis_token_check = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
print(f"UPSTASH_REDIS_REST_URL: {'SET' if _redis_url_check else 'NOT FOUND'}", flush=True)
print(f"UPSTASH_REDIS_REST_TOKEN: {'SET' if _redis_token_check else 'NOT FOUND'}", flush=True)

# ---------------------------------------------------------------------------
# Optional Upstash Redis import — server stays functional without it.
# ---------------------------------------------------------------------------
try:
    from upstash_redis import Redis as _UpstashRedis  # type: ignore[import-untyped]
    _UPSTASH_AVAILABLE = True
except ImportError:
    _UpstashRedis = None  # type: ignore[assignment,misc]
    _UPSTASH_AVAILABLE = False

from agent.orchestrator import Orchestrator
from tools.catalog_search import load_catalog_json

# ---------------------------------------------------------------------------
# Rate-limiting & session-persistence constants
# ---------------------------------------------------------------------------

# Maximum number of user messages allowed in a single session.
# On hitting this cap the server returns a friendly message without calling
# the Orchestrator (zero API cost).
SESSION_MAX_TURNS: int = 6

# Maximum number of /chat calls across ALL sessions per calendar day (UTC).
# Configurable via env so it can be changed without a redeploy.
DAILY_CHAT_LIMIT: int = int(os.getenv("DAILY_CHAT_LIMIT", "50"))

# Redis key namespacing
_SESSION_KEY_PREFIX = "session:"
_DAILY_KEY_PREFIX   = "daily:"

# How long a session lives in Redis after the last message (seconds).
_SESSION_TTL_SEC: int = 7_200  # 2 hours

# Friendly message returned when a session has reached its turn cap.
_SESSION_CAP_MESSAGE = (
    "We've covered a lot of ground! To keep the conversation snappy, "
    "I'll let you start a fresh chat when you're ready to explore more. "
    "Feel free to open a new session any time."
)

# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


def _build_redis_client():
    """Return an Upstash Redis client if credentials exist, else None."""
    if not _UPSTASH_AVAILABLE:
        url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
        if url or token:
            print("Redis client creation failed: upstash_redis library not available", flush=True)
        return None
    url   = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if not url or not token:
        return None
    try:
        client = _UpstashRedis(url=url, token=token)
        print("Redis client created successfully", flush=True)
        return client
    except Exception as e:
        print(f"Redis client creation failed: {e}", flush=True)
        return None


def _serialize_block(block: Any) -> dict:
    """Serialize one content block to a plain dict, preserving every attribute.

    Using the SDK's own model_dump() (Pydantic v2) / dict() (Pydantic v1)
    guarantees that *all* fields — including thinking-block `thinking` /
    `signature` attributes — are captured verbatim, with no silent drops.
    """
    # Pydantic v2
    if hasattr(block, "model_dump"):
        return block.model_dump()
    # Pydantic v1
    if hasattr(block, "dict"):
        return block.dict()
    # Plain dict or custom object — take everything
    if isinstance(block, dict):
        return block
    return vars(block)


def _serialize_messages(messages: list) -> str:
    """Convert the Orchestrator message list to a JSON string for Redis storage.

    Each assistant message's content may contain SDK content-block objects
    (TextBlock, ToolUseBlock, ThinkingBlock …). We serialize every attribute
    of each block so nothing is silently dropped when we round-trip through
    Redis.
    """
    serializable: list = []
    for msg in messages:
        role    = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            # Tool-result or correction messages stored as plain strings
            serializable.append({"role": role, "content": content})
        elif isinstance(content, list):
            serialized_blocks = []
            for block in content:
                serialized_blocks.append(_serialize_block(block))
            serializable.append({"role": role, "content": serialized_blocks})
        else:
            # Fallback — shouldn't happen, but store as-is
            serializable.append({"role": role, "content": content})

    return json.dumps(serializable, ensure_ascii=False, default=str)


def _deserialize_messages(raw: str) -> list:
    """Reconstruct the message list from the JSON stored in Redis.

    Content blocks are kept as plain dicts — the Anthropic Python SDK
    accepts dicts in the messages list (it does not require SDK objects),
    so no reconstruction into typed objects is needed.
    """
    return json.loads(raw)


def _load_session(
    redis_client,
    session_id: str,
) -> Tuple[list, dict, int]:
    """Load (messages, retrieved_by_id, user_turn_count) from Redis.

    Returns empty defaults when the key does not exist (new session).
    """
    key = f"{_SESSION_KEY_PREFIX}{session_id}"
    try:
        raw = redis_client.get(key) if redis_client else None
    except Exception:
        raw = None

    if not raw:
        return [], {}, 0

    try:
        state = json.loads(raw)
        messages         = _deserialize_messages(json.dumps(state.get("messages", [])))
        retrieved_by_id  = state.get("retrieved_by_id", {})
        user_turn_count  = int(state.get("user_turn_count", 0))
        return messages, retrieved_by_id, user_turn_count
    except Exception:
        # Corrupt/stale data — treat as new session
        return [], {}, 0


def _save_session(
    redis_client,
    session_id: str,
    orchestrator: "Orchestrator",
    user_turn_count: int,
) -> None:
    """Persist the Orchestrator's current state to Redis with a TTL.

    We count user_turn_count ourselves (rather than re-deriving from
    orchestrator.messages) so the caller has full control.
    """
    if redis_client is None:
        return

    key = f"{_SESSION_KEY_PREFIX}{session_id}"
    state = {
        "messages": json.loads(_serialize_messages(orchestrator.messages)),
        "retrieved_by_id": orchestrator.retrieved_by_id,
        "user_turn_count": user_turn_count,
    }
    try:
        redis_client.set(key, json.dumps(state, ensure_ascii=False, default=str))
        redis_client.expire(key, _SESSION_TTL_SEC)
    except Exception:
        # Non-fatal — in-memory dict still has the state for this process.
        pass


def _get_daily_count(redis_client) -> int:
    """Return the current daily call count (read-only, no side-effects)."""
    if redis_client is None or DAILY_CHAT_LIMIT <= 0:
        return 0
    today = date.today().isoformat()
    key   = f"{_DAILY_KEY_PREFIX}{today}"
    try:
        raw = redis_client.get(key)
        return int(raw) if raw else 0
    except Exception:
        return 0


def _increment_daily(redis_client) -> None:
    """Increment the daily call counter, setting a 24-hour TTL on first write."""
    if redis_client is None or DAILY_CHAT_LIMIT <= 0:
        return
    today = date.today().isoformat()
    key   = f"{_DAILY_KEY_PREFIX}{today}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            # First request today — set an expiry so the key auto-cleans.
            redis_client.expire(key, 86_400)  # 24 h
    except Exception:
        # Non-fatal — proceed regardless.
        pass


def _check_and_increment_daily(redis_client) -> bool:
    """**LEGACY SHIM** — kept for backward compatibility with existing tests.

    New call-sites should use _get_daily_count() + _increment_daily() directly
    so the counter is only incremented after the per-session cap passes.
    This shim increments first and returns True if the resulting count exceeds
    the limit, preserving the old behaviour for tests that import it.
    """
    if redis_client is None or DAILY_CHAT_LIMIT <= 0:
        return False
    today = date.today().isoformat()
    key   = f"{_DAILY_KEY_PREFIX}{today}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, 86_400)
        return int(count) > DAILY_CHAT_LIMIT
    except Exception:
        return False

# Initialize FastAPI App
app = FastAPI(
    title="AI Shopping Concierge API",
    description="Backend API wrapper for the stateful concierge orchestrator.",
    version="1.0.0",
)

# Add CORS Middleware allowing all localhost origins (with any port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_origin_regex="https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store: session_id -> Orchestrator
sessions: Dict[str, Orchestrator] = {}


# Local helper function to extract most recently retrieved products
def get_latest_retrieved_products(messages: list[dict]) -> list[dict]:
    """Scan backward through conversation history to extract search results."""
    for msg in reversed(messages):
        # Look for the user-role tool results response block
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_use_id = part.get("tool_use_id")

                    # Verify it corresponds to a catalog_search tool call
                    for helper_msg in reversed(messages):
                        if helper_msg.get("role") == "assistant" and isinstance(
                            helper_msg.get("content"), list
                        ):
                            for block in helper_msg["content"]:
                                b_type = getattr(block, "type", None) or (
                                    block.get("type") if isinstance(block, dict) else None
                                )
                                b_name = getattr(block, "name", None) or (
                                    block.get("name") if isinstance(block, dict) else None
                                )
                                b_id = getattr(block, "id", None) or (
                                    block.get("id") if isinstance(block, dict) else None
                                )

                                if (
                                    b_type == "tool_use"
                                    and b_name == "catalog_search"
                                    and b_id == tool_use_id
                                ):
                                    try:
                                        products = json.loads(part.get("content", "[]"))
                                        if isinstance(products, list):
                                            return products
                                    except Exception:
                                        pass
    return []


# Pydantic schemas
class ChatRequest(BaseModel):
    message: str = Field(..., description="User's natural language input message.")
    session_id: str = Field(..., description="Unique session identifier for managing chat history.")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Plain-language assistant response.")
    products: List[Dict[str, Any]] = Field(default=[], description="List of products retrieved during this turn.")
    session_capped: bool = Field(default=False, description="True when the session has reached its turn limit. Frontend can show a 'start a new chat' hint.")


class HealthResponse(BaseModel):
    status: str = Field("ok", description="FastAPI server status.")
    redis_connected: bool = Field(False, description="True when the server successfully reached Upstash Redis.")



@app.get("/api/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def get_health() -> Dict[str, Any]:
    """Verify backend server connectivity and Redis reachability.

    Attempts a trivial Redis GET to confirm the connection is live, so
    deployment issues can be diagnosed without running a full chat turn.
    """
    redis_ok = False
    try:
        r = _build_redis_client()
        if r is not None:
            # A GET on a non-existent key is sufficient to confirm connectivity.
            r.get("__health_probe__")
            redis_ok = True
    except Exception:
        redis_ok = False
    return {"status": "ok", "redis_connected": redis_ok}


@app.get("/api/products", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
def get_products(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all catalog products, optionally filtered by category query param."""
    catalog = load_catalog_json()
    if category:
        cat_lower = category.strip().lower()
        return [p for p in catalog if str(p.get("category", "")).lower() == cat_lower]
    return catalog


@app.get("/api/products/{product_id}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
def get_product_by_id(product_id: str) -> Dict[str, Any]:
    """Return a single product by its unique ID, or 404 if not found."""
    catalog = load_catalog_json()
    pid_lower = product_id.strip().lower()
    for product in catalog:
        if str(product.get("id", "")).lower() == pid_lower:
            return product
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with ID '{product_id}' not found in catalog.",
    )



@app.post("/api/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def post_chat(request: ChatRequest) -> Dict[str, Any]:
    """Process a user shopping request, maintaining state across session_id.

    State is persisted to Upstash Redis (when configured) so conversations
    survive process restarts and horizontal scaling. Falls back to the
    in-memory `sessions` dict when Redis credentials are not set.

    Rate-limiting order (important):
    1. Load session state.
    2. Per-session cap check — returns friendly 200 immediately; daily
       counter is NOT touched (capped sessions cost nothing).
    3. Daily cap read — returns 429 if already at/over the limit, without
       incrementing (no phantom count for rejected requests).
    4. Only after both checks pass: increment daily counter, then call
       the Orchestrator.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication Missing: ANTHROPIC_API_KEY is not set on the server.",
        )

    session_id = request.session_id.strip()
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or empty session_id.",
        )

    # ------------------------------------------------------------------
    # 1. Build Redis client (None → in-memory fallback)
    # ------------------------------------------------------------------
    redis = _build_redis_client()

    # ------------------------------------------------------------------
    # 2. Load session state from Redis (or in-memory dict as fallback)
    # ------------------------------------------------------------------
    if redis is not None:
        prior_messages, prior_retrieved, user_turn_count = _load_session(
            redis, session_id
        )
    elif session_id in sessions:
        # In-memory fallback: reconstruct counts from existing orchestrator
        orch_in_mem = sessions[session_id]
        prior_messages      = orch_in_mem.messages
        prior_retrieved     = orch_in_mem.retrieved_by_id
        user_turn_count     = sum(
            1 for m in orch_in_mem.messages if m.get("role") == "user"
        )
    else:
        prior_messages, prior_retrieved, user_turn_count = [], {}, 0

    # ------------------------------------------------------------------
    # 3. Per-session turn cap (must come before daily counter increment)
    #    A capped session returns immediately — the daily counter is never
    #    touched, so repeated pings on a capped session waste zero quota.
    # ------------------------------------------------------------------
    if user_turn_count >= SESSION_MAX_TURNS:
        return {
            "reply": _SESSION_CAP_MESSAGE,
            "products": [],
            "session_capped": True,
        }

    # ------------------------------------------------------------------
    # 4. Daily global cap — read-only check first, no increment yet.
    #    We only increment AFTER confirming the request will actually
    #    proceed, so rejected requests never consume quota.
    # ------------------------------------------------------------------
    if DAILY_CHAT_LIMIT > 0 and _get_daily_count(redis) >= DAILY_CHAT_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Daily request limit reached. The concierge will be available "
                "again tomorrow. Thank you for your patience."
            ),
        )

    # ------------------------------------------------------------------
    # 5. Increment daily counter — request is confirmed to proceed.
    # ------------------------------------------------------------------
    _increment_daily(redis)

    # ------------------------------------------------------------------
    # 6. Construct Orchestrator with pre-loaded state
    # ------------------------------------------------------------------
    try:
        orchestrator = Orchestrator(
            api_key=api_key,
            verbose=False,
            initial_messages=prior_messages,
            initial_retrieved_by_id=prior_retrieved,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Initialization Error: Failed to start concierge orchestrator: {e}",
        )

    # ------------------------------------------------------------------
    # 7. Run the chat turn
    # ------------------------------------------------------------------
    try:
        reply    = orchestrator.chat(request.message)
        products = get_latest_retrieved_products(orchestrator.messages)
    except Exception as e:
        error_msg = str(e)
        if "credit balance is too low" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Anthropic API Credit Exhaustion: Server api key is out of credits.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Concierge Error: {error_msg}",
        )

    # ------------------------------------------------------------------
    # 8. Persist updated state
    # ------------------------------------------------------------------
    new_turn_count = user_turn_count + 1

    if redis is None:
        print(f"[chat] Session state save ({session_id}): Redis client is None (in-memory fallback)", flush=True)
    else:
        print(f"[chat] Session state save ({session_id}): Redis client is a real client", flush=True)

    if redis is not None:
        _save_session(redis, session_id, orchestrator, new_turn_count)
    else:
        # Keep in-memory dict in sync for this process lifetime.
        sessions[session_id] = orchestrator

    return {"reply": reply, "products": products, "session_capped": False}
