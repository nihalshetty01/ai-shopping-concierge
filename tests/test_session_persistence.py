# -*- coding: utf-8 -*-
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.server import (
    _deserialize_messages,
    _load_session,
    _save_session,
    _serialize_messages,
    _SESSION_KEY_PREFIX,
    _SESSION_TTL_SEC,
)
from agent.orchestrator import Orchestrator

class _MockRedis:
    def __init__(self, preload=None):
        self._store = dict(preload or {})
        self._expiry = {}
        self.set_calls = []
        self.expire_calls = []
    def get(self, key): return self._store.get(key)
    def set(self, key, value):
        self._store[key] = value
        self.set_calls.append((key, value))
    def expire(self, key, seconds):
        self._expiry[key] = seconds
        self.expire_calls.append((key, seconds))
    def incr(self, key):
        v = int(self._store.get(key, 0)) + 1
        self._store[key] = str(v)
        return v

def _make_orch(messages=None, retrieved=None):
    orch = Orchestrator(api_key='test-key', initial_messages=list(messages or []), initial_retrieved_by_id=dict(retrieved or {}))
    class NC:
        class messages:
            @staticmethod
            def create(**k): raise AssertionError('Unexpected API call')
    orch.client = NC()
    return orch

class _TB:
    type = 'text'
    def __init__(self, t): self.text = t
    def model_dump(self): return {'type': self.type, 'text': self.text}

class _KB:
    type = 'thinking'
    def __init__(self, thinking, sig):
        self.thinking = thinking
        self.signature = sig
    def model_dump(self): return {'type': self.type, 'thinking': self.thinking, 'signature': self.signature}

class _UB:
    type = 'tool_use'
    def __init__(self, name, inp, bid='tu_1'):
        self.name = name
        self.input = inp
        self.id = bid
    def model_dump(self): return {'type': self.type, 'name': self.name, 'input': self.input, 'id': self.id}

class TestSerDeser:
    def test_plain_text_rt(self):
        m = [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': [_TB('hello')]}]
        r = _deserialize_messages(_serialize_messages(m))
        assert r[0] == {'role': 'user', 'content': 'hi'}
        assert r[1]['content'][0]['text'] == 'hello'

    def test_tool_use_rt(self):
        b = _UB('catalog_search', {'category': 'laptop', 'budget': 60000}, 'tu_abc')
        r = _deserialize_messages(_serialize_messages([{'role': 'assistant', 'content': [b]}]))
        assert r[0]['content'][0]['id'] == 'tu_abc'
        assert r[0]['content'][0]['input']['budget'] == 60000

    def test_thinking_block_all_fields(self):
        b = _KB(thinking='analyze budget', sig='sig_XYZ')
        r = _deserialize_messages(_serialize_messages([{'role': 'assistant', 'content': [b]}]))
        blk = r[0]['content'][0]
        assert blk['type'] == 'thinking'
        assert blk['thinking'] == 'analyze budget'
        assert blk['signature'] == 'sig_XYZ'

    def test_mixed_content(self):
        m = [{'role': 'assistant', 'content': [_KB('r', 's'), _TB('hi')]}]
        r = _deserialize_messages(_serialize_messages(m))
        assert r[0]['content'][0]['type'] == 'thinking'
        assert r[0]['content'][1]['type'] == 'text'

    def test_plain_dict_passthrough(self):
        m = [{'role': 'assistant', 'content': [{'type': 'text', 'text': 'dict'}]}]
        r = _deserialize_messages(_serialize_messages(m))
        assert r[0]['content'][0]['text'] == 'dict'

    def test_tool_result_rt(self):
        m = [{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'tu_1', 'content': '[]'}]}]
        r = _deserialize_messages(_serialize_messages(m))
        assert r[0]['content'][0]['tool_use_id'] == 'tu_1'

class TestLoadSession:
    def test_missing_key_defaults(self):
        msgs, ret, turns = _load_session(_MockRedis(), 'new')
        assert msgs == [] and ret == {} and turns == 0

    def test_loads_from_redis(self):
        prior = {'messages': [{'role': 'user', 'content': 'laptop'}], 'retrieved_by_id': {}, 'user_turn_count': 1}
        redis = _MockRedis(preload={_SESSION_KEY_PREFIX + 's1': json.dumps(prior)})
        msgs, _, turns = _load_session(redis, 's1')
        assert msgs[0]['content'] == 'laptop' and turns == 1

    def test_loads_retrieved(self):
        prior = {'messages': [], 'retrieved_by_id': {'p1': {'id': 'p1', 'name': 'LX'}}, 'user_turn_count': 2}
        redis = _MockRedis(preload={_SESSION_KEY_PREFIX + 's2': json.dumps(prior)})
        _, ret, _ = _load_session(redis, 's2')
        assert ret['p1']['name'] == 'LX'

    def test_corrupt_returns_defaults(self):
        redis = _MockRedis(preload={_SESSION_KEY_PREFIX + 'bad': 'INVALID'})
        msgs, ret, turns = _load_session(redis, 'bad')
        assert msgs == [] and ret == {} and turns == 0

    def test_none_redis_defaults(self):
        msgs, ret, turns = _load_session(None, 'noop')
        assert msgs == [] and ret == {} and turns == 0

class TestSaveSession:
    def test_writes_key(self):
        redis = _MockRedis()
        _save_session(redis, 'sv', _make_orch(messages=[{'role': 'user', 'content': 'hi'}]), 1)
        assert _SESSION_KEY_PREFIX + 'sv' in {k for k, _ in redis.set_calls}

    def test_sets_ttl(self):
        redis = _MockRedis()
        _save_session(redis, 'ttl', _make_orch(), 0)
        ttls = {k: v for k, v in redis.expire_calls}
        assert ttls.get(_SESSION_KEY_PREFIX + 'ttl') == _SESSION_TTL_SEC

    def test_persists_messages(self):
        redis = _MockRedis()
        _save_session(redis, 'msg', _make_orch(messages=[{'role': 'user', 'content': 'phones'}]), 1)
        state = json.loads(redis._store[_SESSION_KEY_PREFIX + 'msg'])
        assert state['messages'][0]['content'] == 'phones'
        assert state['user_turn_count'] == 1

    def test_persists_retrieved(self):
        redis = _MockRedis()
        _save_session(redis, 'ret', _make_orch(retrieved={'p99': {'id': 'p99', 'name': 'MB'}}), 1)
        state = json.loads(redis._store[_SESSION_KEY_PREFIX + 'ret'])
        assert state['retrieved_by_id']['p99']['name'] == 'MB'

    def test_none_redis_noop(self):
        _save_session(None, 'noop', _make_orch(), 0)

class TestRoundTrip:
    def test_restores_state(self):
        redis = _MockRedis()
        orch = _make_orch(
            messages=[{'role': 'user', 'content': 'laptop 50k'},
                      {'role': 'assistant', 'content': [_TB('Use case?')]}],
            retrieved={'lp01': {'id': 'lp01', 'name': 'Lenovo'}},
        )
        _save_session(redis, 'rt', orch, 1)
        msgs, ret, turns = _load_session(redis, 'rt')
        assert turns == 1
        assert msgs[0]['content'] == 'laptop 50k'
        assert msgs[1]['content'][0]['text'] == 'Use case?'
        assert ret['lp01']['name'] == 'Lenovo'

    def test_thinking_survives_roundtrip(self):
        redis = _MockRedis()
        orch = _make_orch(messages=[{'role': 'assistant', 'content': [_KB('budget analysis', 'sig_ABC'), _TB('Picks.')]}])
        _save_session(redis, 'think', orch, 1)
        msgs, _, _ = _load_session(redis, 'think')
        blocks = msgs[0]['content']
        assert blocks[0]['type'] == 'thinking'
        assert blocks[0]['thinking'] == 'budget analysis'
        assert blocks[0]['signature'] == 'sig_ABC'
        assert blocks[1]['type'] == 'text'
