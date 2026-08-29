"""UI hierarchy → a compact, agent-readable screen index.

The single biggest practical problem with driving Android from an LLM is that a
raw `uiautomator dump` is 50-200 KB of XML per screen. Handing that to a model
burns tens of thousands of tokens for information it mostly cannot use, and the
agent runs out of context after a handful of screens.

This module renders the same hierarchy as one line per *actionable or readable*
element, with a stable `#N` reference the agent can tap:

    #1 [Button] "Sign in" desc=login_button @(540,1320)
    #2 [EditText] "" desc=text_field_Email hint="Email" @(540,980)
    #3 [Text] "Forgot password?" @(540,1450)

That is roughly two orders of magnitude smaller, and it reads like a menu. Raw
XML stays available through a separate, explicitly-named tool for the rare case
where the agent genuinely needs the tree.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

# Widget classes that are always worth showing even with no text or description:
# the agent needs to know an empty input or an unlabelled toggle is there.
ALWAYS_INTERESTING = {
    "android.widget.EditText",
    "android.widget.Button",
    "android.widget.ImageButton",
    "android.widget.CheckBox",
    "android.widget.RadioButton",
    "android.widget.Switch",
    "android.widget.SeekBar",
    "android.widget.Spinner",
    "android.widget.RatingBar",
}

# Friendlier names for the classes that dominate a typical dump.
CLASS_ALIASES = {
    "android.widget.TextView": "Text",
    "android.widget.EditText": "EditText",
    "android.widget.Button": "Button",
    "android.widget.ImageButton": "ImageButton",
    "android.widget.ImageView": "Image",
    "android.widget.CheckBox": "CheckBox",
    "android.widget.RadioButton": "Radio",
    "android.widget.Switch": "Switch",
    "android.widget.SeekBar": "SeekBar",
    "android.widget.ScrollView": "Scroll",
    "android.widget.HorizontalScrollView": "HScroll",
    "androidx.recyclerview.widget.RecyclerView": "List",
    "android.widget.ListView": "List",
    "android.view.View": "View",
    "android.view.ViewGroup": "Group",
    "android.widget.FrameLayout": "Frame",
    "android.widget.LinearLayout": "Row",
    "android.widget.RelativeLayout": "Rel",
    "android.widget.Toast": "Toast",
}


@dataclass
class Element:
    ref: int
    cls: str
    text: str
    desc: str
    rid: str
    hint: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    scrollable: bool
    checkable: bool
    checked: bool
    enabled: bool
    focused: bool
    password: bool
    pkg: str

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def short_class(self) -> str:
        return CLASS_ALIASES.get(self.cls, self.cls.rsplit(".", 1)[-1])

    def label(self) -> str:
        """Best human-facing name, used in error messages."""
        return self.text or self.desc or self.rid.rsplit("/", 1)[-1] or self.short_class

    def render(self) -> str:
        parts = [f"#{self.ref}", f"[{self.short_class}]"]
        if self.text or self.cls == "android.widget.EditText":
            parts.append(f'"{_clip(self.text)}"')
        if self.desc and self.desc != self.text:
            parts.append(f"desc={_token(self.desc)}")
        if self.rid:
            parts.append(f"id={_token(self.rid.rsplit('/', 1)[-1])}")
        if self.hint:
            parts.append(f'hint="{_clip(self.hint)}"')
        flags = []
        if self.checkable:
            flags.append("checked" if self.checked else "unchecked")
        if self.scrollable:
            flags.append("scrollable")
        if not self.enabled:
            flags.append("disabled")
        if self.focused:
            flags.append("focused")
        if self.password:
            flags.append("password")
        if flags:
            parts.append(f"({','.join(flags)})")
        x, y = self.center
        parts.append(f"@({x},{y})")
        return " ".join(parts)

    def to_dict(self) -> dict:
        x, y = self.center
        return {
            "ref": f"#{self.ref}",
            "class": self.short_class,
            "text": self.text,
            "desc": self.desc,
            "id": self.rid,
            "center": [x, y],
            "bounds": list(self.bounds),
            "clickable": self.clickable,
            "enabled": self.enabled,
        }


def _clip(value: str, limit: int = 80) -> str:
    value = value.replace("\n", "\\n")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _token(value: str) -> str:
    """Quote only when the value contains whitespace — keeps common lines short."""
    return value if value and not re.search(r"\s", value) else f'"{_clip(value)}"'


def _bool(node: ET.Element, attr: str) -> bool:
    return node.attrib.get(attr) == "true"


def _parse_bounds(raw: str) -> tuple[int, int, int, int] | None:
    m = BOUNDS_RE.match(raw or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    return x1, y1, x2, y2


def _is_interesting(node: ET.Element, bounds: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = bounds
    if x2 <= x1 or y2 <= y1:
        return False  # zero-area: laid out but not visible
    cls = node.attrib.get("class", "")
    if cls in ALWAYS_INTERESTING:
        return True
    if _bool(node, "clickable") or _bool(node, "long-clickable") or _bool(node, "checkable"):
        return True
    if _bool(node, "scrollable"):
        return True
    return bool(node.attrib.get("text") or node.attrib.get("content-desc"))


def parse(xml_text: str) -> list[Element]:
    """Extract the interesting elements from a hierarchy dump, in document order."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"could not parse UI hierarchy XML: {e}") from e

    elements: list[Element] = []
    ref = 0
    for node in root.iter("node"):
        bounds = _parse_bounds(node.attrib.get("bounds", ""))
        if bounds is None or not _is_interesting(node, bounds):
            continue
        ref += 1
        elements.append(
            Element(
                ref=ref,
                cls=node.attrib.get("class", ""),
                text=node.attrib.get("text", ""),
                desc=node.attrib.get("content-desc", ""),
                rid=node.attrib.get("resource-id", ""),
                hint=node.attrib.get("hint", ""),
                bounds=bounds,
                clickable=_bool(node, "clickable"),
                scrollable=_bool(node, "scrollable"),
                checkable=_bool(node, "checkable"),
                checked=_bool(node, "checked"),
                enabled=_bool(node, "enabled"),
                focused=_bool(node, "focused"),
                password=_bool(node, "password"),
                pkg=node.attrib.get("package", ""),
            )
        )
    return elements


def render(elements: list[Element], header: str | None = None) -> str:
    if not elements:
        body = "(no interactive or readable elements — the screen may still be rendering)"
    else:
        body = "\n".join(e.render() for e in elements)
    return f"{header}\n{body}" if header else body


def find(
    elements: list[Element],
    *,
    ref: str | int | None = None,
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    rid: str | None = None,
    cls: str | None = None,
    index: int = 0,
) -> Element:
    """Resolve a selector to exactly one element, or raise with a useful message.

    Matching is deliberately strict-then-loose: `text`/`desc`/`rid` are exact so a
    recipe cannot silently drift onto a different button, while `contains` exists
    for the cases where the exact string is not known.
    """
    criteria = {"ref": ref, "text": text, "contains": contains, "desc": desc, "id": rid, "class": cls}
    active = {k: v for k, v in criteria.items() if v is not None}
    if not active:
        raise ValueError("no selector given: pass one of ref / text / contains / desc / rid / cls")

    candidates = elements
    if ref is not None:
        wanted = int(str(ref).lstrip("#"))
        candidates = [e for e in candidates if e.ref == wanted]
    if text is not None:
        candidates = [e for e in candidates if e.text == text]
    if contains is not None:
        needle = contains.lower()
        candidates = [e for e in candidates if needle in e.text.lower() or needle in e.desc.lower()]
    if desc is not None:
        candidates = [e for e in candidates if e.desc == desc]
    if rid is not None:
        candidates = [e for e in candidates if e.rid == rid or e.rid.endswith(f"/{rid}")]
    if cls is not None:
        candidates = [e for e in candidates if e.short_class.lower() == cls.lower() or e.cls == cls]

    if not candidates:
        raise LookupError(f"no element matches {active}. Call `screen` to see what is on screen.")
    if index >= len(candidates):
        raise LookupError(f"{active} matched {len(candidates)} element(s); index {index} is out of range")
    return candidates[index]
