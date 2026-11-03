# dl-paper-diagrams

A Claude Code / Agent skill that draws neural-network figures in the style of ML papers. It produces:
- **interactive HTML:** hover for tensor shapes and details, click to trace the data flow, step through the forward pass, filter by tag, export SVG/PNG;
- **static SVG:** for READMEs on GitHub/GitLab, where scripts don't run.

![two-tower example](skills/dl-paper-diagrams/examples/two_tower_lora.svg)

![logit matrix example](skills/dl-paper-diagrams/examples/infonce_logits.svg)

## Install

As a Claude Code plugin, from the terminal:

```bash
npx @anthropic-ai/claude-code plugin install dl-paper-diagrams --marketplace Genndoso/dl-paper-diagrams
```

or inside Claude Code:

```
/plugin install dl-paper-diagrams --marketplace Genndoso/dl-paper-diagrams
```

On Claude Code older than 2.1.275, add the marketplace first:

```bash
npx @anthropic-ai/claude-code plugin marketplace add Genndoso/dl-paper-diagrams
npx @anthropic-ai/claude-code plugin install dl-paper-diagrams@dl-paper-diagrams
```

As a bare skill:

```bash
git clone https://github.com/Genndoso/dl-paper-diagrams /tmp/dlpd && cp -r /tmp/dlpd/skills/dl-paper-diagrams ~/.claude/skills/
```

Then ask Claude for something like *"draw the architecture of this model like in a paper"*.

## Use without Claude

```bash
python3 skills/dl-paper-diagrams/scripts/render.py skills/dl-paper-diagrams/examples/two_tower_lora.json -o out   # out/two_tower_lora.svg + .html
```

The renderer uses the Python standard library only. The spec format is in [references/spec.md](skills/dl-paper-diagrams/references/spec.md), the workflow and style rules in [SKILL.md](skills/dl-paper-diagrams/SKILL.md).

## License

MIT
