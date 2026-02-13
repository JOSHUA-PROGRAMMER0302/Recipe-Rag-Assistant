"""ScaleDown client with a simulated fallback.

This module tries to call a ScaleDown API when `SCALEDOWN_API_URL`
and `SCALEDOWN_API_KEY` env vars are set. If not available it falls
back to a local simulated compression using zlib + base64 so you can
test compression flows without a real API key.
"""
import os
import json
import base64
import zlib
from typing import Dict, Any

try:
    import requests  # optional in some environments
except Exception:
    requests = None


SCALEDOWN_API_KEY = os.environ.get('SCALEDOWN_API_KEY')
SCALEDOWN_API_URL = os.environ.get('SCALEDOWN_API_URL')  # full endpoint, e.g. https://api.scaledown.example/v1/compress


def _simulate_compress(text: str) -> Dict[str, Any]:
    b = text.encode('utf-8')
    comp = zlib.compress(b)
    b64 = base64.b64encode(comp).decode('ascii')
    return {
        'method': 'simulated',
        'compressed_blob_b64': b64,
        'orig_len': len(b),
        'compressed_len': len(comp)
    }


def _simulate_decompress(b64: str) -> str:
    comp = base64.b64decode(b64)
    b = zlib.decompress(comp)
    return b.decode('utf-8')


def compress_text(text: str) -> Dict[str, Any]:
    """Compress `text` via ScaleDown API if configured, otherwise simulate.

    Returns a dictionary with at least: method, compressed_blob_b64, orig_len, compressed_len
    """
    if SCALEDOWN_API_URL and SCALEDOWN_API_KEY and requests is not None:
        headers = {'Authorization': f'Bearer {SCALEDOWN_API_KEY}'}
        try:
            resp = requests.post(SCALEDOWN_API_URL, json={'text': text}, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # Normalize expected fields from real API if present
            if 'compressed_blob_b64' in data or 'blob' in data or 'compressed' in data:
                # prefer explicit b64 key
                blob = data.get('compressed_blob_b64') or data.get('blob') or data.get('compressed')
                return {'method': 'api', 'compressed_blob_b64': blob, 'meta': data}
            return {'method': 'api', 'meta': data}
        except Exception:
            # fall through to simulated
            pass
    return _simulate_compress(text)


def decompress_text(compressed_blob_b64: str, method: str = 'simulated') -> str:
    """Decompress a blob produced by `compress_text`.

    If method='simulated' will zlib-decode; real API blobs may require API calls.
    """
    if method == 'simulated':
        return _simulate_decompress(compressed_blob_b64)
    # If used with real API, you'd call the API's decompress endpoint here.
    raise NotImplementedError('Decompression for method=%s not implemented' % method)

