"""Polite HTTP helper: one shared session, timeouts, size cap, per-host spacing."""
import threading
import time
from urllib.parse import urlparse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
           "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
MAX_BYTES = 2_500_000
MIN_GAP_PER_HOST = 0.8   # seconds between requests to the same host

_local = threading.local()
_last_hit: dict[str, float] = {}
_lock = threading.Lock()


def _session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.s = s
    return s


def _space(host: str):
    with _lock:
        wait = _last_hit.get(host, 0) + MIN_GAP_PER_HOST - time.time()
        _last_hit[host] = time.time() + max(wait, 0)
    if wait > 0:
        time.sleep(wait)


def get(url: str, timeout: float = 10, **kw):
    """Return (status, text, final_url). status 0 means network error."""
    host = urlparse(url).netloc
    _space(host)
    try:
        r = _session().get(url, timeout=timeout, allow_redirects=True, stream=True, **kw)
        chunks, size = [], 0
        for chunk in r.iter_content(65536, decode_unicode=False):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                break
        r._content = b"".join(chunks)
        return r.status_code, r.text, r.url
    except Exception:
        return 0, "", url


def get_json(url: str, timeout: float = 8):
    status, text, final = get(url, timeout=timeout)
    if status != 200:
        return None
    try:
        import json
        return json.loads(text)
    except Exception:
        return None
