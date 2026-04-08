# Oh_My_HLS_Claw

> AI-powered Digital System Design - The True HLS

Oh_My_HLS_Claw is a multi-agent AI system that designs Verilog RTL from natural language descriptions or reference software code. It coordinates specialized agents for planning, module design, verification, documentation, and onboarding.

## Features

- Multi-agent orchestration for architecture planning, RTL generation, verification, docs, and onboarding
- Configurable model routing across OpenAI, Anthropic, Gemini, and Ollama
- Harness loops for iterative refinement between agents
- Checkpoints, resumable project state, and cost tracking
- Icarus Verilog and Vivado simulation backends
- Cross-platform Python workflow with Linux/WSL recommended for smoother EDA tooling
- Multi-language CLI prompts via locale files

## Installation

```bash
pip install -r requirements.txt
python -m src.main init
```

## Platform Notes

- Windows is supported.
- Linux or WSL2 is recommended when using Vivado CLI heavily.
- Vivado integration works wherever `xvlog`, `xelab`, and `xsim` are callable, or where `VIVADO_PATH` points to their directory.

## Usage

```bash
python -m src.main new --desc "8-bit RISC CPU, single cycle, 8 registers"
python -m src.main resume --project my_project
python -m src.main status --project my_project
python -m src.main cost --project my_project
```

## License

MIT
