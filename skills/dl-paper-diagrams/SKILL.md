---
name: dl-paper-diagrams
description: Draws deep-learning architecture figures in the style of ML papers (towers, layer stacks, tensors with shapes, LoRA insets, logit matrices, loss heads) as an interactive HTML page plus a static SVG for READMEs. Use when the user asks for a model/architecture diagram, "схема архитектуры", "как в статье", a figure for a paper or report, a diagram of a loss, attention or logit matrix, or wants an existing mermaid/flowchart architecture diagram to look more like a DL paper.
---

# DL paper diagrams

Turn a model into a figure that reads like one from an ML paper. Write a JSON spec, run `scripts/render.py`, and check the render.
- **Interactive HTML:** hover a block to see its tensor shapes and details, click to trace the data flow, step through an explanation, filter by tag, download SVG or PNG.
- **Static SVG:** same figure, for GitHub/GitLab READMEs, where scripts don't run.

```bash
python3 <skill-dir>/scripts/render.py fig.json -o docs/fig        # -> docs/fig/<name>.svg + <name>.html
python3 <skill-dir>/scripts/render.py fig.json --svg-only          # README only
```

Standard library only, no installs. Full spec reference: [references/spec.md](references/spec.md). Worked examples: `examples/*.json`.

## Workflow

1. **Read the model first.** Get real shapes and hyper-parameters from the code or config: hidden sizes, number of layers, which parts are frozen, the heads, the loss terms. Never invent a number. If one isn't known, write a symbol (`L`, `d`) instead.
2. **Pick figure types.** One idea per figure, usually 2–4 figures:
   - *overview*: inputs → encoder(s) → pooling → head → embedding → similarity → loss;
   - *block detail*: one repeated block (attention / MLP / residuals) with the trainable insets (LoRA `W₀ + BA`, adapters);
   - *objective*: logit/attention matrix with positives, masks, hard negatives and the formula next to it;
   - *inference*: how the trained parts are used at serving time (index, re-ranking, ANN tricks).
3. **Lay out on a grid.** Data flows left → right, and repeated towers stack vertically with dashed "shared θ" links. Use relative coordinates (`"x": "enc.r+40"`) so blocks can be moved as a chain. Keep 30–50px between blocks, and size the canvas so nothing clips.
4. **Encode semantics in colour, not decoration.** The `kind` values are fixed:
   - `frozen` blue, `train` orange, `tensor` grey, `loss` red;
   - `target` green, `side` purple (side inputs), `hard` yellow (hard negatives / highlighted slice), `mask` dark grey.
   Always add a `legend`.
5. **Put shapes everywhere.** Draw a tensor bar with `label` + `dim`, and give each block a `shape` like `[T, 2048] → [2048]` for the tooltip. Use `segments` for concatenations (`[w; z]`) and Matryoshka prefixes.
6. **Add the interactive layer.** For every non-trivial block, set `info` (one or two sentences: what it does and why) and `params` (sizes). `steps` walk the reader through the forward pass; `tags` group blocks (trainable, one tower, the objective).
7. **Render and look at the result.** View the SVG and fix overlaps:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars \
     --window-size=<width>,<height> --screenshot=/tmp/fig.png docs/fig/<name>.svg
   ```
   Then Read the PNG. `qlmanage` thumbnails crop to a square, so don't judge layout by them. To check that the HTML's JS ran, use `--dump-dom file.html | grep '<button'`.
8. **Embed it.** In the README, `![Fig. 1](docs/fig/<name>.svg)` and a link to the `.html` for the interactive version. Formulas go in the surrounding markdown (GitLab: ```` ```math ````, GitHub: `$$`); the figure carries only short labels.

## Style rules (what makes it look like a paper)

- Title as a caption: `"Fig. N. <what it shows>"`. Optional `caption` underneath for the one non-obvious detail.
- Labels are math-like, written with inline markup (`e_{a}`, `ℝ^{2048}`, `W_{0}`, `**bold**`, `` `mono` ``). Unicode: `ℒ φ θ ⊕ ⊃ 𝕊 ℓ₂ ⟨⟩ ×`.
- Repeated stacks: `"stack": true` + `"badge": "× L"`. Trainable insets inside frozen blocks: `"strip": {"kind": "train", "label": ["LoRA", "r=16"]}`.
- Operators as circles (`type: op`: `+`, `⊕`, `·`, `s·cos`). Residual paths run along the side with `via` points.
- Weight sharing: an edge with `"style": "share"` and a label. Optional or inference-only paths: `"style": "dashed"`.
- At most ~25 blocks per figure. Split anything bigger.
- No logos, gradients, shadows or 3D. Fonts stay Helvetica / Menlo.

## When not to use it

Pipelines, infra and data flows (jobs, tables, services) read better as plain mermaid flowcharts. Use this skill for the neural network and its objective.
