# -*- coding: utf-8 -*-
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.server import (
    _check_and_increment_daily,
    _get_daily_count,
    _increment_daily,
    DAILY_CHAT_LIMIT,
    _DAILY_KEY_PREFIX,
    _SESSION_CAP_MESSAGE,
    SESSION_MAX_TURNS,
    _load_session,
    _SESSION_KEY_PREFIX,
)

# ---- Mock Redis ----
class _MockRedis:
    def __init__(self, preload=None):
        self._store = dict(preload or {})
        self.expire_calls = []
    def get(self, key): return self._store.get(key)
    def set(self, key, value): self._store[key] = value
    def expire(self, key, seconds): self.expire_calls.append((key, seconds))
    def incr(self, key):
        v = int(self._store.get(key, 0)) + 1
        self._store[key] = str(v)
        return v

# ---- Helpers ----
def _make_session_state(turn_count: int):
    return {'messages': [], 'retrieved_by_id': {}, 'user_turn_count': turn_count}

# ---- Daily rate limit tests ----
class TestDailyRateLimit:
    def _key(self, date_str=None):
        from datetime import date
        d = date_str or date.today().isoformat()
        return _DAILY_KEY_PREFIX + d

    def test_first_request_not_blocked(self):
        redis = _MockRedis()
        exceeded = _check_and_increment_daily(redis)
        assert not exceeded

    def test_counter_increments(self):
        redis = _MockRedis()
        _check_and_increment_daily(redis)
        _check_and_increment_daily(redis)
        from datetime import date
        key = _DAILY_KEY_PREFIX + date.today().isoformat()
        assert int(redis._store[key]) == 2

    def test_at_limit_is_not_blocked(self):
        from datetime import date
        key = _DAILY_KEY_PREFIX + date.today().isoformat()
        # Pre-seed counter at exactly DAILY_CHAT_LIMIT - 1 so after incr it equals limit
        redis = _MockRedis(preload={key: str(DAILY_CHAT_LIMIT - 1)})
        exceeded = _check_and_increment_daily(redis)
        assert not exceeded

    def test_over_limit_is_blocked(self):
        from datetime import date
        key = _DAILY_KEY_PREFIX + date.today().isoformat()
        # Pre-seed at DAILY_CHAT_LIMIT so next incr exceeds it
        redis = _MockRedis(preload={key: str(DAILY_CHAT_LIMIT)})
        exceeded = _check_and_increment_daily(redis)
        assert exceeded

    def test_different_date_starts_fresh(self):
        # Simulate a counter from yesterday being present but today starting at 0
        old_key = _DAILY_KEY_PREFIX + '2020-01-01'
        redis = _MockRedis(preload={old_key: str(DAILY_CHAT_LIMIT)})
        exceeded = _check_and_increment_daily(redis)
        assert not exceeded

    def test_first_request_sets_expiry(self):
        redis = _MockRedis()
        _check_and_increment_daily(redis)
        from datetime import date
        key = _DAILY_KEY_PREFIX + date.today().isoformat()
        assert any(k == key for k, _ in redis.expire_calls)

    def test_none_redis_never_blocked(self):
        exceeded = _check_and_increment_daily(None)
        assert not exceeded

# ---- Per-session cap tests ----
class TestSessionCap:
    def test_at_max_turns_returns_cap_state(self):
        from datetime import date
        key = _SESSION_KEY_PREFIX + 'sess_full'
        state = _make_session_state(SESSION_MAX_TURNS)
        redis = _MockRedis(preload={key: json.dumps(state)})
        _, _, turns = _load_session(redis, 'sess_full')
        assert turns == SESSION_MAX_TURNS
        # The /chat endpoint would return the cap message
        assert isinstance(_SESSION_CAP_MESSAGE, str) and len(_SESSION_CAP_MESSAGE) > 10

    def test_below_max_turns_not_capped(self):
        from datetime import date
        key = _SESSION_KEY_PREFIX + 'sess_ok'
        state = _make_session_state(SESSION_MAX_TURNS - 1)
        redis = _MockRedis(preload={key: json.dumps(state)})
        _, _, turns = _load_session(redis, 'sess_ok')
        assert turns < SESSION_MAX_TURNS

    def test_cap_message_is_user_friendly(self):
        # The cap message should not expose the raw number or be an error string
        assert str(SESSION_MAX_TURNS) not in _SESSION_CAP_MESSAGE
        assert 'Error' not in _SESSION_CAP_MESSAGE
        assert 'Exception' not in _SESSION_CAP_MESSAGE

    def test_session_max_turns_constant_value(self):
        assert SESSION_MAX_TURNS == 6

# ---- Integration: server endpoint response via TestClient ----
# These use FastAPI's TestClient to exercise the full /api/chat handler logic
# with mocked Upstash Redis and mocked Orchestrator.
class TestChatEndpointRateLimiting:
    def _make_app(self, preloaded_redis=None):
        from api.server import app, _SESSION_KEY_PREFIX
        from fastapi.testclient import TestClient
        import api.server as srv

        # Inject mock redis via monkeypatching _build_redis_client
        mock_redis = _MockRedis(preload=preloaded_redis or {})
        srv._build_redis_client_orig = getattr(srv, '_build_redis_client_orig', None) or srv._build_redis_client
        srv._build_redis_client = lambda: mock_redis

        return TestClient(app, raise_server_exceptions=True), mock_redis

    def teardown_method(self, method):
        import api.server as srv
        # Restore original builder if patched
        if hasattr(srv, '_build_redis_client_orig') and srv._build_redis_client_orig:
            srv._build_redis_client = srv._build_redis_client_orig

    def test_daily_cap_returns_429(self):
        from datetime import date
        import api.server as srv
        mock_redis = _MockRedis(preload={_DAILY_KEY_PREFIX + date.today().isoformat(): str(DAILY_CHAT_LIMIT)})
        srv._build_redis_client = lambda: mock_redis
        from fastapi.testclient import TestClient
        client = TestClient(srv.app, raise_server_exceptions=False)
        resp = client.post('/api/chat', json={'session_id': 'test-daily', 'message': 'hi'})
        assert resp.status_code == 429

    def test_session_cap_returns_200_with_friendly_message(self):
        import api.server as srv
        state = _make_session_state(SESSION_MAX_TURNS)
        mock_redis = _MockRedis(preload={_SESSION_KEY_PREFIX + 'sess_capped': json.dumps(state)})
        srv._build_redis_client = lambda: mock_redis
        from fastapi.testclient import TestClient
        import unittest.mock as mock
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            client = TestClient(srv.app, raise_server_exceptions=False)
            resp = client.post('/api/chat', json={'session_id': 'sess_capped', 'message': 'one more'})
        assert resp.status_code == 200
        data = resp.json()
        assert data['session_capped'] is True
        assert data['reply'] == _SESSION_CAP_MESSAGE
        assert data['products'] == []

    def test_capped_session_does_not_increment_daily_counter(self):
        """A session-capped request must return before touching the daily counter."""
        from datetime import date
        import api.server as srv
        import unittest.mock as mock

        # Pre-seed the session as fully capped, daily counter at 0.
        daily_key = _DAILY_KEY_PREFIX + date.today().isoformat()
        session_key = _SESSION_KEY_PREFIX + 'capped_daily_isolation'
        mock_redis = _MockRedis(preload={
            session_key: json.dumps(_make_session_state(SESSION_MAX_TURNS)),
        })
        srv._build_redis_client = lambda: mock_redis

        from fastapi.testclient import TestClient
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            client = TestClient(srv.app, raise_server_exceptions=False)
            resp = client.post('/api/chat', json={
                'session_id': 'capped_daily_isolation',
                'message': 'extra message',
            })

        # Session cap fires → friendly 200, session_capped=True
        assert resp.status_code == 200
        assert resp.json()['session_capped'] is True

        # Daily counter must be untouched (key absent or still 0)
        daily_val = mock_redis._store.get(daily_key)
        assert daily_val is None or int(daily_val) == 0, (
            f"Daily counter was modified by a capped-session request: {daily_val}"
        )

    def test_daily_cap_check_does_not_increment_on_rejection(self):
        """A request rejected by the daily cap must not consume a quota unit."""
        from datetime import date
        import api.server as srv
        import unittest.mock as mock

        daily_key = _DAILY_KEY_PREFIX + date.today().isoformat()
        # Seed counter at exactly the limit — next allowed request would be rejected.
        mock_redis = _MockRedis(preload={daily_key: str(DAILY_CHAT_LIMIT)})
        srv._build_redis_client = lambda: mock_redis

        from fastapi.testclient import TestClient
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            client = TestClient(srv.app, raise_server_exceptions=False)
            resp = client.post('/api/chat', json={'session_id': 'new-session', 'message': 'hi'})

        # Must be rate-limited
        assert resp.status_code == 429

        # Counter must still be exactly DAILY_CHAT_LIMIT — the rejected request
        # must not have incremented it.
        final_count = int(mock_redis._store.get(daily_key, 0))
        assert final_count == DAILY_CHAT_LIMIT, (
            f"Daily counter was incremented despite rejection: {final_count} (expected {DAILY_CHAT_LIMIT})"
        )


# ---- /api/health endpoint tests ----
class TestHealthEndpoint:
    def teardown_method(self, method):
        import api.server as srv
        if hasattr(srv, '_build_redis_client_orig') and srv._build_redis_client_orig:
            srv._build_redis_client = srv._build_redis_client_orig

    def test_health_redis_connected_false_when_no_credentials(self):
        """/api/health must report redis_connected=false when env vars are absent."""
        import api.server as srv
        import unittest.mock as mock
        from fastapi.testclient import TestClient

        # Patch _build_redis_client to return None (simulates missing credentials)
        srv._build_redis_client_orig = getattr(srv, '_build_redis_client_orig', None) or srv._build_redis_client
        srv._build_redis_client = lambda: None

        client = TestClient(srv.app, raise_server_exceptions=False)
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert data['redis_connected'] is False

    def test_health_redis_connected_true_when_client_responds(self):
        """/api/health must report redis_connected=true when the client successfully pings Redis."""
        import api.server as srv
        import unittest.mock as mock
        from fastapi.testclient import TestClient

        # A mock client whose .get() succeeds (no exception)
        working_redis = _MockRedis()
        srv._build_redis_client_orig = getattr(srv, '_build_redis_client_orig', None) or srv._build_redis_client
        srv._build_redis_client = lambda: working_redis

        client = TestClient(srv.app, raise_server_exceptions=False)
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['redis_connected'] is True

    def test_health_redis_connected_false_when_client_raises(self):
        """/api/health must report redis_connected=false when the Redis call throws."""
        import api.server as srv
        import unittest.mock as mock
        from fastapi.testclient import TestClient

        class _BrokenRedis:
            def get(self, key): raise ConnectionError("unreachable")

        srv._build_redis_client_orig = getattr(srv, '_build_redis_client_orig', None) or srv._build_redis_client
        srv._build_redis_client = lambda: _BrokenRedis()

        client = TestClient(srv.app, raise_server_exceptions=False)
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['redis_connected'] is False
