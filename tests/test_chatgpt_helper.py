import json

import pytest

from perf_agent import chatgpt_helper as ch


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


def test_chatgpt_decide_success(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')

    payload = {
        'output_text': json.dumps(
            {
                'assistant_reply': 'I can create scripts.',
                'action': 'create_scripts',
                'scenario': {
                    'application': 'PetStore',
                    'domain': 'petstore.octoperf.com',
                    'users': 200,
                    'ramp_seconds': 180,
                    'duration_seconds': 1800,
                    'transactions': ['Launch', 'Login', 'Search'],
                },
            }
        )
    }

    def fake_post(url, headers, json, timeout):  # noqa: A002
        return _FakeResponse(status_code=200, payload=payload)

    monkeypatch.setattr(ch.requests, 'post', fake_post)
    result = ch.chatgpt_decide([{'role': 'user', 'content': 'create scripts for petstore'}])
    assert result['action'] == 'create_scripts'
    assert result['scenario']['application'] == 'PetStore'


def test_chatgpt_decide_requires_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ch.ChatGPTError):
        ch.chatgpt_decide([{'role': 'user', 'content': 'hello'}])
