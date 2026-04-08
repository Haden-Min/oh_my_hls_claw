# CLI Command Reference

This file collects the commands currently exposed by `python -m src.main`.

## Overview

```bash
python -m src.main --help
```

Available subcommands:

- `init`
- `new`
- `resume`
- `status`
- `cost`
- `clean`

## `init`

Interactive setup for language, model access, and simulator configuration.

```bash
python -m src.main init
```

What it does:

- chooses UI language
- configures LLM access
- configures simulator selection
- writes settings to `config/settings.yaml`

## `new`

Starts a new generated hardware project from natural language or a reference file.

```bash
python -m src.main new --desc "8-bit ALU supporting ADD, SUB, AND, OR, XOR"
python -m src.main new --ref examples/alu.py
python -m src.main new --project custom_name --desc "single-cycle CPU"
python -m src.main new --approve-all --desc "8-bit register file"
```

Options:

- `--desc DESC`
  - natural-language design request
- `--ref REF`
  - path to reference software code to use as input
- `--board BOARD`
  - target FPGA board name override
- `--project PROJECT`
  - explicit project name override
- `--approve-all`
  - auto-approves interactive checkpoints for the current run

Notes:

- if neither `--desc` nor `--ref` is supplied, the CLI prompts for a description
- generated outputs land under `workspace/<project_name>/`

## `resume`

Shows the saved state for an existing project.

```bash
python -m src.main resume --project my_project
```

Required options:

- `--project PROJECT`

## `status`

Prints the current saved project status.

```bash
python -m src.main status --project my_project
```

Required options:

- `--project PROJECT`

## `cost`

Prints the saved cost breakdown for a project run.

```bash
python -m src.main cost --project my_project
```

Required options:

- `--project PROJECT`

## `clean`

Removes generated project outputs without touching source files.

```bash
python -m src.main clean --project my_project
python -m src.main clean --all
```

Mutually exclusive options:

- `--project PROJECT`
  - removes one project's generated outputs
- `--all`
  - removes all generated outputs under `workspace/` and any safe-to-detect legacy project output folders

Safety notes:

- this command is intended for generated artifacts only
- protected source directories such as `src/`, `config/`, `tests/`, and `docs/` are not treated as removable project outputs

## Quick Help Checks

You can inspect the parser directly at any time:

```bash
python -m src.main --help
python -m src.main new --help
python -m src.main clean --help
python -m src.main resume --help
python -m src.main status --help
python -m src.main cost --help
```
