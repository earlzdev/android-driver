"""Diagnostic logging.

stdout is reserved for the MCP JSON-RPC frame under the stdio transport, so
EVERY diagnostic write in this package goes to stderr. Corrupting stdout with a
stray print() breaks the protocol in a way that is very hard to debug from the
client side.
"""

from __future__ import annotations

import sys
import time


def log(component: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] [{component}] {msg}", file=sys.stderr, flush=True)
