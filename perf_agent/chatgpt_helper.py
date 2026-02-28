"""OpenAI ChatGPT integration for the agent helper box."""
from __future__ import annotations

import json
import os
from typing import Dict, List

import requests


class ChatGPTError(RuntimeError):
    pass


def chatgpt_decide(messages: List[Dict[str, str]]) -> Dict[str, object]:
    """Call OpenAI and return structured decision payload.

    Expected result:
      {
        "assistant_reply": "...",
        "action": "none|create_scripts|run_full_lifecycle",
        "scenario": {...}
      }
    """
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise ChatGPTError('OPENAI_API_KEY is not set.')

    model = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
    base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    url = f'{base_url}/responses'

    system_prompt = (
        'You are a performance engineering copilot. '
        'Extract scenario details for JMeter load testing and respond in strict JSON only. '
        'JSON schema: {"assistant_reply": string, "action": "none|create_scripts|run_full_lifecycle", '
        '"scenario": {"application": string, "domain": string, "users": integer, '
        '"ramp_seconds": integer, "duration_seconds": integer, "transactions": string[]}}. '
        'If user asks to execute/create scripts, choose create_scripts. '
        'If user asks to run load test end-to-end, choose run_full_lifecycle. '
        'If unclear, action=none and ask one concise clarification in assistant_reply. '
        'Always include scenario with best-effort defaults.'
    )

    input_items = [{'role': 'system', 'content': system_prompt}]
    for msg in messages:
        role = str(msg.get('role') or 'user')
        content = str(msg.get('content') or '')
        if not content:
            continue
        input_items.append({'role': role, 'content': content})

    payload = {
        'model': model,
        'input': input_items,
        'temperature': 0.2,
    }

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise ChatGPTError(f'OpenAI request failed: {exc}') from exc

    if response.status_code >= 400:
        raise ChatGPTError(f'OpenAI API error {response.status_code}: {response.text[:500]}')

    data = response.json()
    text = _extract_response_text(data)
    parsed = _parse_json_payload(text)
    if not isinstance(parsed, dict):
        raise ChatGPTError('ChatGPT returned non-JSON response.')

    # normalize minimal shape
    assistant_reply = str(parsed.get('assistant_reply') or '').strip()
    action = str(parsed.get('action') or 'none').strip().lower()
    if action not in ('none', 'create_scripts', 'run_full_lifecycle'):
        action = 'none'
    scenario = parsed.get('scenario')
    if not isinstance(scenario, dict):
        scenario = {}
    return {
        'assistant_reply': assistant_reply or 'Prepared scenario.',
        'action': action,
        'scenario': scenario,
        'model': model,
    }


def _extract_response_text(data: Dict[str, object]) -> str:
    # Preferred shortcut when available
    output_text = data.get('output_text')
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    # Walk output/content blocks
    output = data.get('output')
    if not isinstance(output, list):
        return ''
    chunks: List[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get('content')
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get('text')
            if isinstance(text, str):
                chunks.append(text)
    return '\n'.join(chunks)


def _parse_json_payload(text: str):
    raw = (text or '').strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first JSON object block
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = raw[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return {}
    return {}
