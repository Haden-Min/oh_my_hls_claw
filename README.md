# Oh_My_HLS_Claw

> Natural language in, Verilog RTL out.
> A multi-agent hardware design pipeline for planning, coding, verification, documentation, and FPGA onboarding.

Oh_My_HLS_Claw is a Python-based orchestration system that turns a design request or reference software into:

- architecture specs
- module-by-module Verilog RTL
- testbenches and simulation logs
- engineering documentation
- FPGA onboarding assets

It is built around a set of specialized sub-agents that talk to each other through structured messages and harness loops instead of acting like one giant prompt blob.

## Why It Exists

Typical HLS tools stop at C/C++ to RTL conversion.
Oh_My_HLS_Claw is aiming at a wider workflow:

```text
design intent -> architecture spec -> module plan -> RTL -> testbench -> simulation
-> docs -> board onboarding files
```

It is especially useful if you want an agentic flow that can:

- break large designs into modules
- keep a resumable project state
- run verification as part of the loop
- swap LLM providers and models per sub-agent

## What You Need Installed

You do not need everything on day one.
The fastest path is: Python + OpenAI OAuth proxy + Icarus Verilog.

### Required

- Python 3.11+
- `pip`
- At least one usable LLM path:
  - OpenAI OAuth proxy via `openai-oauth` and Codex login
  - OpenAI API key
  - Anthropic API key
  - Google Gemini API key
  - Ollama local model

### Recommended

- WSL2 Ubuntu or Linux for smoother EDA tooling
- Git

### Optional Simulators

- Icarus Verilog
  - commands used: `iverilog`, `vvp`
  - recommended for quick local iteration
- Vivado CLI
  - commands used: `xvlog`, `xelab`, `xsim`
  - useful when you want closer FPGA-tool flow integration

Windows is supported.
Linux or WSL2 is recommended, especially if you expect to use Vivado CLI heavily.

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Prepare your LLM access

Recommended OAuth-based flow:

```bash
npx @openai/codex login
npx openai-oauth
```

Keep the OAuth proxy running in the background.
The default endpoint expected by this project is:

```text
http://127.0.0.1:10531/v1
```

### 3. Install a simulator

Icarus on Ubuntu / WSL:

```bash
sudo apt update
sudo apt install -y iverilog
iverilog -V
vvp -V
```

Vivado CLI:

- install Vivado normally
- make sure `xvlog`, `xelab`, and `xsim` are callable
- or provide the Vivado `bin` path during `init`

### 4. Run interactive setup

```bash
python -m src.main init
```

### 5. Start your first project

```bash
python -m src.main new --desc "8-bit ALU supporting ADD, SUB, AND, OR, XOR"
```

## Example `init` Flow

This is the kind of interactive setup flow you should expect:

```text
Oh_My_HLS_Claw - Initial Setup

Select language [en/ko/ja/zh] (default: en): en

OpenAI OAuth proxy detected at http://127.0.0.1:10531/v1
Available models: gpt-5.4, gpt-5.3-codex, gpt-5.4-mini
Press Enter for recommended OAuth setup, or type [a] for advanced provider setup:

Simulator [icarus/vivado] (default: icarus): icarus

Configuration saved.
Next step: run `python -m src.main new --desc "8-bit RISC CPU"`
```

If the OAuth proxy is not running, the CLI falls back to API-key or advanced-provider setup.

## Main Commands

```bash
python -m src.main init
python -m src.main new --desc "8-bit RISC CPU, single cycle, 8 registers"
python -m src.main new --ref examples/alu.py
python -m src.main resume --project my_project
python -m src.main status --project my_project
python -m src.main cost --project my_project
```

## Project Layout

The repo is organized around a few core ideas: config, agent logic, LLM backends, simulator wrappers, and generated workspace artifacts.

```text
oh_my_hls_claw/
|- CODEX.md
|- README.md
|- requirements.txt
|- setup.py
|- .env.example
|- .gitignore
|- config/
|  |- models.yaml
|  |- settings.yaml
|  `- prompts/
|     |- planner.md
|     |- manager.md
|     |- rtl_designer.md
|     |- verifier.md
|     |- guide_writer.md
|     `- onboarder.md
|- locale/
|  |- en.yaml
|  |- ko.yaml
|  `- ja.yaml
|- examples/
|  `- alu.py
|- src/
|  |- main.py
|  |- orchestrator.py
|  |- harness.py
|  |- agents/
|  |- llm/
|  |- sim/
|  `- utils/
|- tests/
|  |- test_agents.py
|  |- test_harness.py
|  `- test_sim.py
`- workspace/
   `- <project_name>/
      |- spec/
      |- rtl/
      |- tb/
      |- sim/
      |- docs/
      `- onboard/
```

## Generated Workspace Layout

When you run a project, outputs land under `workspace/<project_name>/`.

- `spec/`: architecture spec and design-step data
- `rtl/`: generated Verilog modules
- `tb/`: generated testbenches
- `sim/`: simulation logs and temporary artifacts
- `docs/`: step reports and final project docs
- `onboard/`: constraints, wrappers, and build helpers

## Configuration Files You Will Actually Touch

### `config/models.yaml`

This file controls which model each sub-agent uses.
If you want to tune quality, speed, or provider choice, this is the first place to edit.

Current default philosophy:

- `planner`: strong reasoning model
- `manager`: strong reasoning model
- `rtl_designer`: Codex-oriented coding model
- `verifier`: Codex-oriented coding/review model
- `guide_writer`: smaller model for docs
- `onboarder`: coding-oriented model because it emits real build assets

### `config/settings.yaml`

This file controls runtime behavior.

Important fields:

- `system.language`: CLI locale
- `system.max_parallel_agents`: concurrency limit
- `system.harness_max_iterations`: max agent loop count
- `system.checkpoint_*`: when approvals are requested
- `openai.use_oauth_proxy`: whether OAuth proxy is the default path
- `openai.oauth_proxy_url`: local OpenAI-compatible proxy endpoint
- `simulator.type`: `icarus` or `vivado`
- `simulator.vivado_path`: optional Vivado `bin` directory

## Sub-Agents

The system is split into specialized agents instead of one monolithic generator.

| Agent | What It Does | Prompt File |
|------|------|------|
| Planner | Turns raw intent into an architecture spec and design steps | `config/prompts/planner.md` |
| Manager | Coordinates project state, step readiness, and completion | `config/prompts/manager.md` |
| RTL Designer | Produces synthesizable Verilog-2001 | `config/prompts/rtl_designer.md` |
| Verifier | Writes testbenches, reviews RTL, and issues pass/fail verdicts | `config/prompts/verifier.md` |
| Guide Writer | Produces step docs and final project writeups | `config/prompts/guide_writer.md` |
| Onboarder | Emits constraints, wrappers, and build/onboarding assets | `config/prompts/onboarder.md` |

Implementation code lives under:

- `src/agents/`

Prompt templates live under:

- `config/prompts/`

## Core Runtime Pieces

If you want to navigate the codebase quickly, start here:

- `src/main.py`: CLI entrypoint
- `src/orchestrator.py`: end-to-end project flow
- `src/harness.py`: agent-to-agent refinement loop
- `src/llm/router.py`: provider/model routing
- `src/sim/icarus_runner.py`: Icarus simulation backend
- `src/sim/vivado_runner.py`: Vivado simulation backend
- `src/utils/checkpoint.py`: approval flow
- `src/utils/file_manager.py`: file persistence

## Verification Status

Current local checks used during development:

```bash
python -m unittest discover -s tests -v
python -m compileall src tests
python -m src.main --help
```

## Platform Notes

- Windows is supported.
- WSL2 or Linux is recommended for smoother simulator and EDA workflows.
- Vivado is not Linux-only in this project design.
- If `xvlog`, `xelab`, and `xsim` are callable, or `vivado_path` points to the right `bin` directory, the Vivado backend can be used.

## License

MIT
