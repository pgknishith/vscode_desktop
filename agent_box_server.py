"""Serve the visual page and provide API endpoints for the helper box.

Usage:
  python agent_box_server.py --port 8010
Then open:
  http://localhost:8010/agent_visual.html
"""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from perf_agent.box_agent import (
    run_box_workflow,
    run_box_workflow_for_request,
    scenario_request_from_dict,
)
from perf_agent.chatgpt_helper import ChatGPTError, chatgpt_decide


ROOT_DIR = Path(__file__).resolve().parent


class AgentBoxHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):  # noqa: N802
        path = self.path.rstrip('/')
        if path not in ('/api/agent', '/api/chat'):
            self.send_error(HTTPStatus.NOT_FOUND, 'Not Found')
            return

        length = int(self.headers.get('Content-Length', '0') or '0')
        body_bytes = self.rfile.read(length)
        try:
            payload = json.loads(body_bytes.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            self._send_json({'status': 'error', 'error': 'Invalid JSON body'}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == '/api/agent':
            self._handle_agent(payload)
            return
        if path == '/api/chat':
            self._handle_chat(payload)
            return

    def _handle_agent(self, payload: Dict[str, Any]):
        prompt = str(payload.get('prompt', '')).strip()
        run_full = bool(payload.get('run_full', False))
        if not prompt:
            self._send_json({'status': 'error', 'error': 'Prompt is required'}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            result = run_box_workflow(prompt=prompt, run_full_lifecycle=run_full, base_dir=str(ROOT_DIR))
        except Exception as exc:
            self._send_json({'status': 'error', 'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(result, status=HTTPStatus.OK)

    def _handle_chat(self, payload: Dict[str, Any]):
        messages_raw = payload.get('messages')
        execute = bool(payload.get('execute', False))
        force_run_full = bool(payload.get('run_full', False))
        if not isinstance(messages_raw, list) or not messages_raw:
            self._send_json({'status': 'error', 'error': 'messages must be a non-empty list'}, status=HTTPStatus.BAD_REQUEST)
            return

        messages = []
        for item in messages_raw:
            if not isinstance(item, dict):
                continue
            role = str(item.get('role') or 'user').strip().lower()
            if role not in ('user', 'assistant', 'system'):
                role = 'user'
            content = str(item.get('content') or '').strip()
            if not content:
                continue
            messages.append({'role': role, 'content': content})
        if not messages:
            self._send_json({'status': 'error', 'error': 'No valid messages supplied'}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            decision = chatgpt_decide(messages)
        except ChatGPTError as exc:
            self._send_json({'status': 'error', 'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json({'status': 'error', 'error': f'ChatGPT integration failed: {exc}'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        response_payload: Dict[str, Any] = {
            'status': 'ok',
            'assistant_reply': decision.get('assistant_reply'),
            'action': decision.get('action'),
            'scenario': decision.get('scenario'),
            'model': decision.get('model'),
        }

        if execute:
            try:
                req = scenario_request_from_dict(
                    decision.get('scenario') if isinstance(decision.get('scenario'), dict) else {},
                    raw_text=messages[-1]['content'],
                )
                should_run_full = force_run_full or decision.get('action') == 'run_full_lifecycle'
                result = run_box_workflow_for_request(
                    req=req,
                    run_full_lifecycle=should_run_full,
                    base_dir=str(ROOT_DIR),
                )
                response_payload['execution'] = result
            except Exception as exc:
                response_payload['execution'] = {'status': 'error', 'error': str(exc)}

        self._send_json(response_payload, status=HTTPStatus.OK)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip('/') == '/api/health':
            self._send_json(
                {
                    'status': 'ok',
                    'service': 'agent-box-server',
                    'api': '/api/agent',
                    'chat_api': '/api/chat',
                },
                status=HTTPStatus.OK,
            )
            return
        return super().do_GET()

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self._send_cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')


def main():
    parser = argparse.ArgumentParser(description='Serve agent visual page with backend API.')
    parser.add_argument('--port', type=int, default=8010, help='HTTP port')
    args = parser.parse_args()

    server = ThreadingHTTPServer(('127.0.0.1', args.port), AgentBoxHandler)
    print(f'Serving on http://127.0.0.1:{args.port}/agent_visual.html')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down server...')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
