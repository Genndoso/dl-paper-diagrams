#!/usr/bin/env python3
"""Render a DL-paper-style diagram spec (JSON) to an interactive HTML page and a static SVG.

    python3 render.py spec.json [-o out_dir] [--svg-only | --html-only] [--dark]

No dependencies beyond the standard library. See SKILL.md for the spec format.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- palette ---
# kind -> (fill, stroke). Paper convention: blue = frozen, orange = trainable,
# grey = tensor / activation, red = loss, green = target / positive, purple = side input.
KINDS = {
    "frozen": ("#dcebf7", "#3f74a8"),
    "train": ("#fde3c8", "#d17a22"),
    "tensor": ("#eeeeee", "#777777"),
    "loss": ("#f7d4d4", "#b33a3a"),
    "target": ("#d3ebd3", "#4b8b4b"),
    "side": ("#e6d9f2", "#7a52a0"),
    "hard": ("#fbe9b7", "#b8901c"),
    "mask": ("#d9d9d9", "#9a9a9a"),
    "plain": ("#ffffff", "#444444"),
    "op": ("#ffffff", "#444444"),
}
DARK = {  # same semantics, tuned for a dark page
    "frozen": ("#1f3a55", "#6fa3d6"), "train": ("#5a3714", "#f0a050"), "tensor": ("#3a3a3a", "#9a9a9a"),
    "loss": ("#5a2323", "#e06b6b"), "target": ("#1f4a2a", "#6cc07a"), "side": ("#3d2a55", "#b58be0"),
    "hard": ("#55461a", "#e0bd4a"), "mask": ("#4a4a4a", "#8a8a8a"), "plain": ("#1e1e1e", "#bbbbbb"),
    "op": ("#1e1e1e", "#bbbbbb"),
}
LEGEND_NAMES = {"frozen": "frozen", "train": "trainable", "tensor": "tensor", "loss": "loss", "target": "target / positive",
                "side": "side input", "hard": "hard negative", "mask": "masked"}
FONT = "Helvetica, Arial, sans-serif"
MONO = "Menlo, Consolas, monospace"


# ------------------------------------------------------------- markup -------
def rich(s: str) -> str:
    """Inline math-ish markup -> SVG tspans: x_{i}, x^{2}, x_i, x^2, **bold**, `mono`."""
    s = html.escape(str(s), quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r'<tspan font-weight="bold">\1</tspan>', s)
    s = re.sub(r"`(.+?)`", rf'<tspan font-family="{MONO}">\1</tspan>', s)
    # tspans with baseline-shift; dy reset keeps following text on the baseline
    s = re.sub(r"_\{(.+?)\}", r'<tspan baseline-shift="sub" font-size="70%">\1</tspan>', s)
    s = re.sub(r"\^\{(.+?)\}", r'<tspan baseline-shift="super" font-size="70%">\1</tspan>', s)
    # bare x_i / x^2: one character, after a short symbol — so identifiers like zelda_v2 or qual_w stay intact
    s = re.sub(r"(?<![A-Za-z]{3})_([A-Za-z0-9])(?![A-Za-z0-9])", r'<tspan baseline-shift="sub" font-size="70%">\1</tspan>', s)
    s = re.sub(r"(?<![A-Za-z]{3})\^([A-Za-z0-9])(?![A-Za-z0-9])", r'<tspan baseline-shift="super" font-size="70%">\1</tspan>', s)
    return s


def plain(s: str) -> str:
    """Markup stripped, for tooltips and <title>."""
    s = re.sub(r"[_^]\{(.+?)\}", r"\1", str(s))
    return re.sub(r"\*\*|`", "", s)


# ------------------------------------------------------------- geometry -----
class Layout:
    """Resolves numeric or relative coordinates: "enc.r+40", "enc.cy", "enc.b+10-5"."""

    def __init__(self):
        self.box: dict[str, tuple[float, float, float, float]] = {}

    def val(self, v, default=0.0):
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        m = re.fullmatch(r"\s*([A-Za-z0-9_\-]+)\.(l|r|t|b|cx|cy|w|h)\s*((?:[+\-]\s*\d+(?:\.\d+)?\s*)*)", v)
        if not m:
            return float(eval(v, {"__builtins__": {}}, {}))  # plain arithmetic like "120+40"
        x, y, w, h = self.box[m.group(1)]
        base = {"l": x, "r": x + w, "t": y, "b": y + h, "cx": x + w / 2, "cy": y + h / 2, "w": w, "h": h}[m.group(2)]
        return base + sum(float(t.replace(" ", "")) for t in re.findall(r"[+\-]\s*\d+(?:\.\d+)?", m.group(3)))

    def anchor(self, ref: str):
        """'id' | 'id.r' | 'id.l' | 'id.t' | 'id.b' | 'id.tl' … -> (x, y, side)."""
        nid, _, side = ref.partition(".")
        x, y, w, h = self.box[nid]
        pts = {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y), "b": (x + w / 2, y + h),
               "c": (x + w / 2, y + h / 2)}
        if side and side[0] in "lrtb" and len(side) > 1 and re.fullmatch(r"[lrtb][+\-]\d+", side):
            # offset along the side: "id.r+10" shifts down 10px on the right side
            base = pts[side[0]]
            off = float(side[1:])
            return (base[0] + off, base[1], side[0]) if side[0] in "tb" else (base[0], base[1] + off, side[0])
        return (*pts[side or "c"], side or "c")


# ------------------------------------------------------------- render -------
class Renderer:
    def __init__(self, spec: dict, dark: bool = False):
        self.spec = spec
        self.pal = DARK if dark else KINDS
        self.ink = "#e8e8e8" if dark else "#222222"
        self.sub = "#aaaaaa" if dark else "#555555"
        self.bg = "#141414" if dark else "#ffffff"
        self.L = Layout()
        self.out: list[str] = []
        self.meta: dict[str, dict] = {}
        self.edges_meta: list[dict] = []

    # -- primitives
    def text(self, x, y, s, size=13, anchor="middle", color=None, bold=False, mono=False, italic=False, cls=""):
        attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color or self.ink}"'
        if bold:
            attrs += ' font-weight="bold"'
        if mono:
            attrs += f' font-family="{MONO}"'
        if italic:
            attrs += ' font-style="italic"'
        if cls:
            attrs += f' class="{cls}"'
        self.out.append(f"<text {attrs}>{rich(s)}</text>")

    def lines_in_box(self, x, y, w, h, lines, size, mono=False):
        n = len(lines)
        for i, ln in enumerate(lines):
            sz = size if i == 0 else size - 1.5
            cy = y + h / 2 + (i - (n - 1) / 2) * (size + 4) + sz * 0.35
            self.text(x + w / 2, cy, ln, size=sz, bold=(i == 0 and n > 1), color=self.ink if i == 0 else self.sub,
                      mono=mono and i == 0)

    # -- nodes
    def node(self, n: dict):
        t = n.get("type", "block")
        nid = n.get("id") or f"_n{len(self.L.box)}"
        kind = n.get("kind", {"tensor": "tensor", "op": "op", "group": "plain", "text": "plain"}.get(t, "frozen"))
        fill, stroke = self.pal.get(kind, self.pal["plain"])
        x, y = self.L.val(n.get("x")), self.L.val(n.get("y"))
        w = self.L.val(n.get("w"), {"tensor": 22, "op": 26, "text": 0}.get(t, 120))
        h = self.L.val(n.get("h"), {"tensor": 80, "op": 26, "text": 0}.get(t, 48))
        if n.get("center"):   # x, y given as centre
            x, y = x - w / 2, y - h / 2
        self.L.box[nid] = (x, y, w, h)
        tags = " ".join(f"tag-{t_}" for t_ in n.get("tags", []))
        info = {"title": plain(n.get("title") or (n.get("label") or [nid])[0] if isinstance(n.get("label"), list)
                               else n.get("title") or n.get("label") or nid),
                "shape": n.get("shape", ""), "info": n.get("info", ""), "params": n.get("params", ""), "kind": kind}
        interactive = t not in ("text", "group") or n.get("info")
        if interactive:
            self.meta[nid] = info
        g_attr = f'id="{nid}" class="node {tags}{" ia" if interactive else ""}" data-kind="{kind}"'
        self.out.append(f"<g {g_attr}>")
        tip = " · ".join(v for v in (info["title"], info["shape"], plain(info["info"])) if v)
        if interactive:
            self.out.append(f"<title>{html.escape(tip)}</title>")
        label = n.get("label", [])
        if isinstance(label, str):
            label = [label]
        size = n.get("size", 13)
        if t == "group":
            self.out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{self.sub}" '
                            f'stroke-width="1" stroke-dasharray="5 4"/>')
            if label:
                self.text(x + 12, y + 20, label[0], size=size, anchor="start", bold=True)
        elif t == "text":
            anchor = n.get("anchor", "start")
            for i, ln in enumerate(label):
                self.text(x, y + i * (size + 5), ln, size=size, anchor=anchor,
                          color=self.sub if n.get("muted") else self.ink, mono=n.get("mono", False),
                          bold=n.get("bold", False))
        elif t == "op":
            r = w / 2
            self.out.append(f'<circle cx="{x + r}" cy="{y + r}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
            self.text(x + r, y + r + size * 0.36, label[0] if label else "+", size=size + 2)
        elif t == "tensor":
            segs = n.get("segments")   # [[fraction, kind, label], ...] stacked top -> bottom
            if segs:
                yy = y
                for frac, k, _lab in segs:
                    f_, s_ = self.pal.get(k, self.pal["tensor"])
                    hh = h * frac
                    self.out.append(f'<rect x="{x}" y="{yy:.1f}" width="{w}" height="{hh:.1f}" fill="{f_}" stroke="{s_}" stroke-width="1.1"/>')
                    if _lab and len(plain(_lab)) <= 2 and w >= 18 and hh >= 14:   # short label fits inside
                        self.text(x + w / 2, yy + hh / 2 + 4, _lab, size=11, mono=True)
                    elif _lab:
                        side = n.get("seg_labels", "right")
                        lx = x - 6 if side == "left" else x + w + 6
                        self.text(lx, yy + hh / 2 + 4, _lab, size=11, anchor="end" if side == "left" else "start",
                                  color=self.sub, mono=True)
                    yy += hh
            else:
                self.out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="1.1"/>')
            if label:
                self.text(x + w / 2, y - 7, label[0], size=size, mono=True)
            if n.get("dim"):
                self.text(x + w / 2, y + h + 14, n["dim"], size=11, color=self.sub)
        elif t == "matrix":
            self.matrix(n, x, y)
        else:  # block
            dash = ' stroke-dasharray="5 4"' if n.get("dashed") else ""
            self.out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{n.get("rx", 7)}" fill="{fill}" '
                            f'stroke="{stroke}" stroke-width="1.4"{dash}/>')
            if n.get("stack"):          # "× L" repeated-block look
                for k_ in range(1, 3):
                    self.out.insert(-1, f'<rect x="{x + 4 * k_}" y="{y - 4 * k_}" width="{w}" height="{h}" rx="{n.get("rx", 7)}" '
                                        f'fill="{fill}" stroke="{stroke}" stroke-width="1" opacity="{0.6 - 0.2 * k_}"/>')
            strip = n.get("strip")      # trainable inset inside a frozen block, e.g. {"kind": "train", "label": ["LoRA", "r=16"]}
            if strip:
                sw = strip.get("w", 46)
                sf, ss = self.pal.get(strip.get("kind", "train"))
                self.out.append(f'<rect x="{x + w - sw - 6}" y="{y + 6}" width="{sw}" height="{h - 12}" rx="5" fill="{sf}" '
                                f'stroke="{ss}" stroke-width="1.3"/>')
                self.lines_in_box(x + w - sw - 6, y + 6, sw, h - 12, strip.get("label", []), 11)
                w -= sw + 6
            self.lines_in_box(x, y, w, h, label, size, mono=n.get("mono", False))
            if n.get("badge"):          # small tag in the top corner, e.g. "× L", "❄"; left when a strip takes the right
                bx, ba = (x + 8, "start") if strip else (x + w - 6, "end")
                self.text(bx, y + 14, n["badge"], size=10, anchor=ba, color=stroke, bold=True)
        self.out.append("</g>")

    def matrix(self, n, x, y):
        """Logit / attention matrix: rows × cols cells, cells: {"r,c": kind}, diag: kind, row/col labels."""
        rows, cols, cs = n["rows"], n["cols"], n.get("cell", 40)
        gaps = set(n.get("col_gaps", []))  # column indices before which a gap is drawn
        cells = {tuple(map(int, k.split(","))): v for k, v in n.get("cells", {}).items()}
        marks = {"target": "+", "mask": "×", "hard": "−"}
        cx = []
        xx = x
        for j in range(cols):
            if j in gaps:
                xx += 10
            cx.append(xx)
            xx += cs
        for i in range(rows):
            for j in range(cols):
                k = cells.get((i, j)) or (n.get("diag") if i == j and j < rows else None) or n.get("col_kind", {}).get(str(j)) \
                    or n.get("fill", "tensor")
                f_, s_ = self.pal.get(k, self.pal["tensor"])
                self.out.append(f'<rect class="cell" data-r="{i}" data-c="{j}" x="{cx[j]}" y="{y + i * cs}" width="{cs}" '
                                f'height="{cs}" fill="{f_}" stroke="{s_}" stroke-width="1"/>')
                if n.get("marks", True) and k in marks:
                    self.text(cx[j] + cs / 2, y + i * cs + cs / 2 + 6, marks[k], size=16, color=self.ink)
        for j, lab in enumerate(n.get("col_labels", [])):
            self.text(cx[j] + cs / 2, y - 10, lab, size=12, mono=True)
        for i, lab in enumerate(n.get("row_labels", [])):
            self.text(x - 10, y + i * cs + cs / 2 + 5, lab, size=12, mono=True, anchor="end")
        for i, lab in enumerate(n.get("row_right", [])):
            self.text(xx + 12, y + i * cs + cs / 2 + 5, lab, size=12, mono=True, anchor="start", color=self.pal["side"][1])
        self.L.box[n.get("id", "_m")] = (x, y, xx - x, rows * cs)

    # -- edges
    def edge(self, e: dict, idx: int):
        x1, y1, s1 = self.L.anchor(e["from"])
        x2, y2, s2 = self.L.anchor(e["to"])
        pts = [(x1, y1)]
        for p in e.get("via", []):
            pts.append((self.L.val(p[0]), self.L.val(p[1])))
        if not e.get("via") and e.get("route", "auto") != "straight":
            if s1 in "lr" and s2 in "lr" and abs(y1 - y2) > 0.5:
                mx = (x1 + x2) / 2 if e.get("mid") is None else self.L.val(e["mid"])
                pts += [(mx, y1), (mx, y2)]
            elif s1 in "tb" and s2 in "tb" and abs(x1 - x2) > 0.5:
                my = (y1 + y2) / 2 if e.get("mid") is None else self.L.val(e["mid"])
                pts += [(x1, my), (x2, my)]
            elif s1 in "lr" and s2 in "tb":
                pts.append((x2, y1))
            elif s1 in "tb" and s2 in "lr":
                pts.append((x1, y2))
        pts.append((x2, y2))
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        style = e.get("style", "solid")
        color = self.pal.get(e["kind"], self.pal["plain"])[1] if e.get("kind") else (self.sub if style == "dashed" else self.ink)
        dash = ' stroke-dasharray="5 4"' if style in ("dashed", "share") else ""
        head = "" if e.get("arrow", style != "share") is False else ' marker-end="url(#ar)"'
        src, dst = e["from"].split(".")[0], e["to"].split(".")[0]
        eid = f"e{idx}"
        self.edges_meta.append({"id": eid, "from": src, "to": dst})
        tags = " ".join(f"tag-{t_}" for t_ in e.get("tags", []))
        self.out.append(f'<path id="{eid}" class="edge {tags}" d="{d}" fill="none" stroke="{color}" stroke-width="1.4"{dash}{head}/>')
        if e.get("label"):
            # label at the middle of the longest segment
            segs = list(zip(pts, pts[1:]))
            (ax, ay), (bx, by) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
            lx, ly = (ax + bx) / 2, (ay + by) / 2
            horiz = abs(by - ay) < abs(bx - ax)
            self.text(lx + (0 if horiz else 6), ly + (-6 if horiz else 4), e["label"], size=11, color=self.sub,
                      anchor="middle" if horiz else "start", mono=e.get("mono", False))

    def legend(self, kinds, y):
        x = 20
        for k in kinds:
            name = LEGEND_NAMES.get(k, k) if isinstance(k, str) else k[1]
            k = k if isinstance(k, str) else k[0]
            f_, s_ = self.pal[k]
            self.out.append(f'<rect x="{x}" y="{y - 10}" width="14" height="12" fill="{f_}" stroke="{s_}"/>')
            self.text(x + 20, y, name, size=11, anchor="start", color=self.sub)
            x += 34 + 6.5 * len(name)

    def render(self) -> str:
        s = self.spec
        W, H = s.get("width", 1200), s.get("height", 500)
        if s.get("title"):
            self.text(W / 2, 28, s["title"], size=16, bold=True)
        body_start = len(self.out)
        for n in s.get("nodes", []):
            self.node(n)
        nodes_svg = self.out[body_start:]
        self.out = self.out[:body_start]
        for i, e in enumerate(s.get("edges", [])):
            self.edge(e, i)
        self.out += nodes_svg   # edges under nodes
        for n in s.get("notes", []):   # free text, formulas
            self.text(self.L.val(n["x"]), self.L.val(n["y"]), n["text"], size=n.get("size", 12),
                      anchor=n.get("anchor", "middle"), color=self.sub if n.get("muted") else None, mono=n.get("mono", False))
        if s.get("legend"):
            self.legend(s["legend"], H - 14)
        if s.get("caption"):
            self.text(W / 2, H - (36 if s.get("legend") else 12), s["caption"], size=12, color=self.sub, italic=True)
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
                f'font-family="{FONT}">\n<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{self.ink}"/></marker>'
                f'</defs>\n<rect width="{W}" height="{H}" fill="{self.bg}"/>\n')
        return head + "\n".join(self.out) + "\n</svg>\n"


# ------------------------------------------------------------- html ---------
HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fafafa;--card:#fff;--ink:#222;--sub:#666;--line:#ddd;--acc:#d17a22}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#111;--card:#1b1b1b;--ink:#e8e8e8;--sub:#aaa;--line:#333;--acc:#f0a050}}
:root[data-theme="dark"]{--bg:#111;--card:#1b1b1b;--ink:#e8e8e8;--sub:#aaa;--line:#333;--acc:#f0a050}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Helvetica,Arial,sans-serif}
main{max-width:1280px;margin:0 auto;padding:16px}
h1{font-size:18px;margin:4px 0 10px}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px}
button{font:inherit;font-size:12px;padding:4px 10px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:6px;cursor:pointer}
button.on{border-color:var(--acc);color:var(--acc)}
.fig{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px;overflow:auto}
.fig svg{display:block;max-width:100%;height:auto}
.node.ia{cursor:pointer}
.node.ia:hover > rect,.node.ia:hover > circle{filter:brightness(0.93);stroke-width:2.2}
.dim{opacity:.18;transition:opacity .15s}
.hl > rect,.hl > circle{stroke-width:2.6 !important}
path.edge.hl{stroke-width:2.6 !important;stroke:var(--acc) !important}
#tip{position:fixed;pointer-events:none;max-width:340px;background:var(--card);color:var(--ink);border:1px solid var(--line);
 border-radius:8px;padding:8px 10px;font-size:12.5px;box-shadow:0 4px 18px rgba(0,0,0,.15);display:none;z-index:9}
#tip b{display:block;margin-bottom:2px}#tip code{font-family:Menlo,Consolas,monospace;font-size:12px;color:var(--acc)}
#tip .k{color:var(--sub);font-size:11px}
#step{min-height:22px;color:var(--sub);margin:8px 2px 0}
.cap{color:var(--sub);font-size:13px;margin:8px 2px}
</style></head><body><main>
<h1>__TITLE__</h1>
<div class="bar" id="bar"></div>
<div class="fig" id="fig">__SVG__</div>
<div id="step"></div>
<p class="cap">Hover a block for shapes and details · click to trace its data flow · click empty space to reset.</p>
</main><div id="tip"></div>
<script>
const META=__META__, EDGES=__EDGES__, TAGS=__TAGS__, STEPS=__STEPS__;
const svg=document.querySelector('#fig svg'), tip=document.getElementById('tip'), bar=document.getElementById('bar');
const $=id=>svg.getElementById?svg.getElementById(id):document.getElementById(id);
svg.querySelectorAll('title').forEach(t=>t.remove());
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function fmt(s){return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/_\\{([^}]+)\\}/g,'<sub>$1</sub>').replace(/\\^\\{([^}]+)\\}/g,'<sup>$1</sup>')}
svg.querySelectorAll('.node.ia').forEach(g=>{
  const m=META[g.id]; if(!m) return;
  g.addEventListener('mousemove',ev=>{
    tip.innerHTML='<b>'+fmt(m.title)+'</b>'+(m.shape?'<div><code>'+fmt(m.shape)+'</code></div>':'')+
      (m.info?'<div>'+fmt(m.info)+'</div>':'')+(m.params?'<div class="k">params: '+fmt(m.params)+'</div>':'')+
      '<div class="k">'+m.kind+'</div>';
    tip.style.display='block';
    const x=Math.min(ev.clientX+14,innerWidth-360), y=Math.min(ev.clientY+14,innerHeight-tip.offsetHeight-10);
    tip.style.left=x+'px'; tip.style.top=y+'px';});
  g.addEventListener('mouseleave',()=>tip.style.display='none');
  g.addEventListener('click',ev=>{ev.stopPropagation();trace(g.id)});
});
function reset(){svg.querySelectorAll('.dim,.hl').forEach(e=>e.classList.remove('dim','hl'));document.getElementById('step').textContent=''}
function highlight(nodes,edges){
  svg.querySelectorAll('.node,.edge').forEach(e=>e.classList.add('dim'));
  nodes.forEach(n=>{const e=$(n); if(e){e.classList.remove('dim');e.classList.add('hl')}});
  edges.forEach(n=>{const e=$(n); if(e){e.classList.remove('dim');e.classList.add('hl')}});}
function trace(id){
  const nodes=new Set([id]),edges=new Set();
  for(const dir of ['from','to']){const other=dir==='from'?'to':'from';let front=[id];
    while(front.length){const nx=[];for(const n of front)for(const e of EDGES)if(e[dir]===n&&!edges.has(e.id)){edges.add(e.id);
      if(!nodes.has(e[other])){nodes.add(e[other]);nx.push(e[other])}}front=nx}}
  highlight(nodes,edges);}
document.getElementById('fig').addEventListener('click',reset);
function btn(label,fn){const b=document.createElement('button');b.textContent=label;b.onclick=()=>fn(b);bar.appendChild(b);return b}
TAGS.forEach(t=>btn(t.label||t.tag,b=>{const on=!b.classList.contains('on');bar.querySelectorAll('button.tag').forEach(x=>x.classList.remove('on'));
  reset(); if(on){b.classList.add('on');const ns=[...svg.querySelectorAll('.node.tag-'+t.tag)].map(e=>e.id),
  es=[...svg.querySelectorAll('.edge.tag-'+t.tag)].map(e=>e.id);highlight(ns,es);document.getElementById('step').textContent=t.info||''}}).classList.add('tag'));
if(STEPS.length){let k=-1;const show=()=>{reset();if(k<0)return;const s=STEPS[k];highlight(s.nodes||[],
  EDGES.filter(e=>(s.nodes||[]).includes(e.from)&&(s.nodes||[]).includes(e.to)).map(e=>e.id).concat(s.edges||[]));
  document.getElementById('step').innerHTML='<b>'+(k+1)+'/'+STEPS.length+'</b> '+fmt(s.text||'')};
  btn('◀ step',()=>{k=Math.max(-1,k-1);show()});btn('step ▶',()=>{k=Math.min(STEPS.length-1,k+1);show()});}
btn('SVG ⤓',()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([svg.outerHTML],{type:'image/svg+xml'}));
  a.download='__NAME__.svg';a.click()});
btn('PNG ⤓',()=>{const vb=svg.viewBox.baseVal,c=document.createElement('canvas');c.width=vb.width*2;c.height=vb.height*2;
  const img=new Image();img.onload=()=>{c.getContext('2d').drawImage(img,0,0,c.width,c.height);c.toBlob(b=>{const a=document.createElement('a');
  a.href=URL.createObjectURL(b);a.download='__NAME__.png';a.click()})};
  img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg.outerHTML)});
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", default=None, help="output dir (default: next to the spec)")
    ap.add_argument("--svg-only", action="store_true")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--dark", action="store_true", help="dark palette for the static SVG")
    a = ap.parse_args()
    p = Path(a.spec)
    spec = json.loads(p.read_text())
    out = Path(a.out) if a.out else p.parent
    out.mkdir(parents=True, exist_ok=True)
    name = spec.get("name", p.stem)
    r = Renderer(spec, dark=a.dark)
    svg = r.render()
    missing = [e for e in r.edges_meta if e["from"] not in r.L.box or e["to"] not in r.L.box]
    if missing:
        sys.exit(f"edges reference unknown nodes: {missing}")
    if not a.html_only:
        (out / f"{name}.svg").write_text(svg)
    if not a.svg_only:
        page = (HTML.replace("__TITLE__", html.escape(plain(spec.get("page_title") or spec.get("title", name))))
                .replace("__NAME__", name)
                .replace("__META__", json.dumps(r.meta, ensure_ascii=False))
                .replace("__EDGES__", json.dumps(r.edges_meta))
                .replace("__TAGS__", json.dumps(spec.get("tags", []), ensure_ascii=False))
                .replace("__STEPS__", json.dumps(spec.get("steps", []), ensure_ascii=False))
                .replace("__SVG__", svg.replace('<?xml version="1.0"?>', "")))
        (out / f"{name}.html").write_text(page)
    print("wrote", *(str(out / f"{name}.{ext}") for ext in ("svg", "html")
                     if not (ext == "svg" and a.html_only) and not (ext == "html" and a.svg_only)))


if __name__ == "__main__":
    main()
