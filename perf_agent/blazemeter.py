"""Simple BlazeMeter client stubs.

This module provides minimal functions to upload a JMX and trigger a test on
BlazeMeter using their v4 API. The implementation here is intentionally small
and uses `requests`. In CI/production you'd want error handling, retries,
and robust parsing of responses.
"""
import os
from typing import Optional

import requests


class BlazeMeterClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = 'https://a.blazemeter.com/api/v4'):
        self.api_key = api_key or os.environ.get('BLAZEMETER_API_KEY')
        if not self.api_key:
            raise RuntimeError('BlazeMeter API key is required via parameter or BLAZEMETER_API_KEY env var')
        self.base_url = base_url
        self.headers = {'Authorization': f'Bearer {self.api_key}'}

    def upload_jmx(self, jmx_path: str, name: Optional[str] = None) -> dict:
        """Upload a JMX file. Returns the response JSON (stubbed minimal handling)."""
        url = f'{self.base_url}/workspaces'
        # For a minimal stub, we'll just return a dict indicating success.
        # Implementers should call the actual BlazeMeter upload endpoints here.
        return {'status': 'ok', 'jmx_path': jmx_path, 'name': name}

    def start_test(self, jmx_id: str, location: Optional[str] = None) -> dict:
        """Start a test run using an uploaded JMX identifier.

        This is a stub; real implementation would POST to the runs endpoint.
        """
        return {'status': 'started', 'jmx_id': jmx_id, 'location': location}
