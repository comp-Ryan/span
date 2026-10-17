"""Server-side workflow picture: layered top-to-bottom layout of the run's nodes, as SVG."""
from __future__ import annotations

from xml.sax.saxutils import escape

W, H, GAP_X, GAP_Y, PAD = 136, 56, 12, 22, 8
NEUTRAL = {"fill": "#f6f3ee", "stroke": "#d8d1c5", "text": "#2a2723", "sub": "#8a8378"}
STYLES = {
    "context": NEUTRAL, "scoring": NEUTRAL, "forecast": NEUTRAL, "levers": NEUTRAL,
    "answer": {"fill": "#ff7a45", "stroke": "#ff7a45", "text": "#ffffff", "sub": "#ffe3d6"},
    "action": {"fill": "#ececec", "stroke": "#c4c4c4", "text": "#333333", "sub": "#777777"},
    "decision": {"fill": "#fff1cc", "stroke": "#e0a526", "text": "#4a3a10", "sub": "#9a7a2a"},
}


def layout(nodes: list[dict]) -> dict[str, tuple[float, float]]:
    """Depth = distance from root; siblings spread around their parent's x, then overlaps are swept apart."""
    by_id = {n["id"]: n for n in nodes}
    depth: dict[str, int] = {}

    def d(nid: str) -> int:
        if nid not in depth:
            p = by_id[nid].get("parent")
            depth[nid] = 0 if p not in by_id else d(p) + 1
        return depth[nid]

    layers: dict[int, list[dict]] = {}
    for n in nodes:
        layers.setdefault(d(n["id"]), []).append(n)
    xs: dict[str, float] = {}
    for lvl in sorted(layers):
        want = []
        groups: dict[str | None, list[dict]] = {}
        for n in layers[lvl]:
            groups.setdefault(n.get("parent") if n.get("parent") in by_id else None, []).append(n)
        roots = groups.pop(None, [])
        for i, n in enumerate(roots):
            want.append((i * (W + GAP_X), n["id"]))
        for p, kids in groups.items():
            for i, n in enumerate(kids):
                want.append((xs[p] + (i - (len(kids) - 1) / 2) * (W + GAP_X), n["id"]))
        want.sort()
        last = None
        for x, nid in want:
            if last is not None and x < last + W + GAP_X:
                x = last + W + GAP_X
            xs[nid] = last = x
    shift = PAD - min(xs.values(), default=0)
    return {nid: (x + shift, PAD + depth[nid] * (H + GAP_Y)) for nid, x in xs.items()}


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"


def _wrap(s: str, n: int = 19, lines: int = 2) -> list[str]:
    out, cur = [], ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > n:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    out.append(cur)
    return out[: lines - 1] + [_clip(" ".join(out[lines - 1:]), n)] if len(out) > lines else out


def render_svg(nodes: list[dict], decided: dict[str, str] | None = None) -> str:
    """`decided` maps node_id -> "open" | "resolved" for nodes that carried a decision (drawn amber)."""
    decided = decided or {}
    pos = layout(nodes)
    width = max((x for x, _ in pos.values()), default=0) + W + PAD
    height = max((y for _, y in pos.values()), default=0) + H + PAD
    out = [(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="Helvetica, Arial, sans-serif">')]
    for n in nodes:
        p = n.get("parent")
        if p in pos:
            (px, py), (cx, cy) = pos[p], pos[n["id"]]
            x1, y1, x2, y2 = px + W / 2, py + H, cx + W / 2, cy
            my = (y1 + y2) / 2
            out.append(f'<path d="M{x1:.1f},{y1:.1f} C{x1:.1f},{my:.1f} {x2:.1f},{my:.1f} {x2:.1f},{y2:.1f}" '
                       f'fill="none" stroke="#b8b0a3" stroke-width="1.4"/>')
    for n in nodes:
        x, y = pos[n["id"]]
        s = STYLES["decision"] if n["id"] in decided else STYLES.get(n["type"], NEUTRAL)
        stroke = "#d64545" if n.get("status") == "failed" else s["stroke"]
        dash = ' stroke-dasharray="4,3"' if n.get("status") in ("running", "waiting") else ""
        sub = n["type"].upper() + " \u00b7 " + n.get("status", "")
        if n["id"] in decided:
            sub += " \u00b7 " + ("decided" if decided[n["id"]] == "resolved" else "needs you")
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{W}" height="{H}" rx="7" ry="7" fill="{s["fill"]}" '
                   f'stroke="{stroke}" stroke-width="1.4"{dash}/>')
        for i, line in enumerate(_wrap(n.get("title", ""))):
            out.append(f'<text x="{x + 9:.1f}" y="{y + 17 + i * 14:.1f}" font-size="12" font-weight="bold" '
                       f'fill="{s["text"]}">{escape(line)}</text>')
        out.append(f'<text x="{x + 9:.1f}" y="{y + H - 8:.1f}" font-size="8.5" fill="{s["sub"]}">'
                   f'{escape(_clip(sub, 30))}</text>')
    out.append("</svg>")
    return "\n".join(out)
