# Spec reference

A spec is one JSON object. Coordinates are in SVG pixels, origin at the top left.

```jsonc
{
  "name": "fig_arch",               // output file stem (default: spec file stem)
  "title": "Fig. 1. …",              // drawn at the top
  "page_title": "…",                 // HTML <title>, defaults to title
  "width": 1200, "height": 480,
  "legend": ["frozen", "train", "tensor", "loss"],   // kinds, or [kind, "custom name"]
  "caption": "…",                    // italic line above the legend
  "nodes": [ … ],                    // drawn in order; a node may reference earlier ones
  "edges": [ … ],                    // drawn under the nodes
  "notes": [{"x": 0, "y": 0, "text": "…", "size": 12, "anchor": "middle", "muted": true, "mono": false}],
  "tags":  [{"tag": "lora", "label": "trainable", "info": "shown under the figure when active"}],
  "steps": [{"nodes": ["a", "b"], "edges": [], "text": "explanation for this step"}]
}
```

## Coordinates

`x`, `y`, `w`, `h` take a number, plain arithmetic (`"120+40"`), or a reference to an earlier node:
`"<id>.<l|r|t|b|cx|cy|w|h>[+N][-N]"`. For example, `"x": "enc.r+40"` places the node 40px right of `enc`.
`"center": true` treats `x`, `y` as the centre.

## Node types

| type | look | specific fields |
|---|---|---|
| `block` (default) | rounded box; the first label line is bold, the rest muted | `label` [lines], `kind`, `stack`, `badge`, `strip`, `dashed`, `rx`, `mono` |
| `tensor` | flat bar | `label` (above), `dim` (below), `segments` [[fraction, kind, label], …] top→bottom, `seg_labels`: `right` / `left` |
| `op` | circle, `w` = diameter | `label`: `["+"]`, `["⊕"]`, `["s·cos"]` |
| `matrix` | grid of cells | `rows`, `cols`, `cell`, `diag` kind, `cells` {"r,c": kind}, `col_kind` {"j": kind}, `col_gaps` [j], `col_labels`, `row_labels`, `row_right`, `marks` (default true: + × −) |
| `group` | dashed frame with a bold caption | `label` |
| `text` | free text lines | `label` [lines], `size`, `anchor`, `muted`, `mono`, `bold` |

Fields common to all types: `id`, `kind`, `size` (font size), `tags` [..].
Interactive-layer fields: `title`, `shape`, `info`, `params`. The tooltip shows them; the static SVG keeps them as `<title>`.

`kind` values: `frozen`, `train`, `tensor`, `loss`, `target`, `side`, `hard`, `mask`, `plain`, `op`.

## Edges

```jsonc
{"from": "enc.r", "to": "pool.l", "label": "H ∈ ℝ^{T×d}", "style": "solid|dashed|share", "kind": "train",
 "via": [["enc.r+20", "enc.cy"], ["enc.r+20", "pool.cy"]], "mid": "pool.l-20", "route": "auto|straight",
 "arrow": true, "tags": ["lora"]}
```

- Anchors: `id` (centre), `id.l`, `id.r`, `id.t`, `id.b`. An offset along the side: `id.l+30` (30px down the left side), `id.t-20` (20px left along the top).
- Auto routing:
  - side → side: elbow at the midpoint, or at `mid` if set;
  - side → top/bottom: one bend.
- `via` gives explicit bend points.
- `share` draws a dashed line with no arrow head.

## Inline markup

`x_{i}`, `x^{2}` → subscript/superscript; bare `x_i`, `x^2` only after a 1–2-letter symbol (so `zelda_v2`, `qual_w` stay as is); `**bold**`; `` `mono` ``. Markup is supported in labels, notes and tooltips.
