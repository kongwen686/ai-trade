from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import ssl

import certifi


@lru_cache(maxsize=1)
def create_default_ssl_context() -> ssl.SSLContext:
    default_paths = ssl.get_default_verify_paths()
    cafile = default_paths.cafile or default_paths.openssl_cafile
    if cafile and Path(cafile).exists():
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())
