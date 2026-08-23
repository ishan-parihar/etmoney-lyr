"""Low-level extraction of embedded data from ET Money pages.

Two mechanisms:
1. JS var blocks: ``var NAME = {...}`` / ``var NAME = [...]`` in classic SSR pages
   (fund detail, compare). Extracted with a string-aware balanced-brace scan.
2. Next.js RSC flight payloads: ``self.__next_f.push([1,"..."])`` chunks on stock
   pages, reassembled and scanned for JSON objects by key.
"""

import json
import re

_UNESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})|\\u\{([0-9a-fA-F]+)\}")
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_OPENERS = {"{": "}", "[": "]"}


def _decode_js_string(s: str) -> str:
    """Decode a JS double-quoted string body: \\uXXXX escapes + standard escapes."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            simple = {
                "n": "\n",
                "t": "\t",
                "r": "\r",
                '"': '"',
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
            }
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            m = _UNESCAPE_RE.match(s, i)
            if m:
                cp = int(m.group(1) or m.group(2), 16)
                out.append(chr(cp))
                i += m.end() - i
                continue
        out.append(c)
        i += 1
    return "".join(out)


def extract_rsc_payload(html: str) -> str:
    """Reassemble all Next.js flight-data chunks from an HTML page.

    Returns "" when the page carries no RSC payload.
    """
    chunks = _PUSH_RE.findall(html)
    return "".join(_decode_js_string(c) for c in chunks)


def extract_balanced(text: str, start: int) -> str | None:
    """Return the raw text of the JSON-ish value starting at ``start`` ('{' or '[').

    String-aware: ignores braces inside double-quoted strings and escape sequences.
    Returns None if unbalanced/truncated.
    """
    opener = text[start]
    closer = _OPENERS[opener]
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return None


def extract_js_var(page_html: str, var_name: str) -> str | None:
    """Extract the raw value of ``var <name> = {…`` / ``[…]`` from page HTML."""
    m = re.search(r"\bvar\s+" + re.escape(var_name) + r"\s*=\s*(?=[\[{])", page_html)
    if not m:
        return None
    return extract_balanced(page_html, m.end())


def parse_js_var(page_html: str, var_name: str) -> object:
    """extract_js_var + json.loads; returns None when missing or not valid JSON.

    Some vars are JS literals with unquoted keys — those come back as None here;
    use find_key/regex fallbacks for them.
    """
    raw = extract_js_var(page_html, var_name)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def find_json_objects(payload: str, key: str, limit: int = 5) -> list[dict]:
    """Scan an RSC payload for JSON objects that contain ``key`` at top level.

    Returns up to ``limit`` unique parsed objects.
    """
    results: list[dict] = []
    seen: set[int] = set()
    needle = f'"{key}":'
    idx = payload.find(needle)
    while idx != -1 and len(results) < limit * 4:
        # Walk backwards to the opening brace of the enclosing object.
        start = payload.rfind("{", 0, idx)
        if start != -1:
            raw = extract_balanced(payload, start)
            if raw:
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict) and key in obj and id(obj) not in seen:
                        seen.add(id(obj))
                        results.append(obj)
                        if len(results) >= limit:
                            break
                except (ValueError, RecursionError):
                    pass
        idx = payload.find(needle, idx + len(needle))
    return results[:limit]


def find_value(payload: str, key: str, limit: int = 5) -> list[object]:
    """Extract the balanced JSON values of ``"key": <value>`` occurrences.

    Unlike find_json_objects this returns the value itself (array or object),
    which is what RSC payloads use for collection fields like ``stockList``.
    """
    out: list[object] = []
    needle = f'"{key}":'
    idx = payload.find(needle)
    while idx != -1 and len(out) < limit:
        j = idx + len(needle)
        while j < len(payload) and payload[j] in " \t\r\n":
            j += 1
        if j < len(payload) and payload[j] in _OPENERS:
            raw = extract_balanced(payload, j)
            if raw:
                try:
                    out.append(json.loads(raw))
                except (ValueError, RecursionError):
                    pass
        idx = payload.find(needle, idx + len(needle))
    return out


def find_key(raw: str, key: str) -> str | None:
    """Regex-extract a single scalar field from a possibly non-JSON JS literal."""
    m = re.search(r'"?' + re.escape(key) + r'"?\s*:\s*("(?:[^"\\]|\\.)*"|[^,}\]]+)', raw)
    if not m:
        return None
    val = m.group(1).strip()
    if val.startswith('"'):
        try:
            val = json.loads(val)
        except ValueError:
            val = val.strip('"')
    return val
