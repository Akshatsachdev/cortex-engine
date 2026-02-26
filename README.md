# 🧠 Cortex Engine

> A secure, local-first AI execution runtime that converts natural language tasks into controlled, policy-governed tool actions.

Cortex Engine is **not a chatbot**.
It is a structured AI execution system designed for **determinism, security, and auditability**.

---

# 🚀 Overview

Cortex Engine transforms natural language instructions into structured tool execution — safely.

It:

* Accepts natural language tasks
* Generates strict JSON execution plans via local LLM
* Validates plans with Pydantic schemas
* Enforces a policy engine
* Executes only registered tools
* Logs every action to append-only audit logs
* Supports GPU acceleration
* Provides automatic model failover

Cortex is built as infrastructure, not experimentation.

---

# ❌ What Cortex Is NOT

* ❌ Not an autonomous agent
* ❌ Not cloud-dependent
* ❌ Not internet-connected by default
* ❌ Not a chat assistant
* ❌ Not uncontrolled AI execution

Every action is:

* Schema validated
* Policy validated
* Tool restricted
* Logged
* Deterministic

---

# 🏗 Architecture

```text
User Task
   ↓
LLM Planner (strict JSON only)
   ↓
JSON Extraction Layer
   ↓
Pydantic Schema Validation
   ↓
Policy Engine Validation
   ↓
Tool Registry Execution
   ↓
Append-only JSONL Audit Logs
```

Project structure:

```text
cortex/
│
├── agent/          → Execution loop + models
├── llm/            → Planner + llama-cpp provider
├── tools/          → Tool registry + SAFE tools
├── security/       → Policy validation
├── runtime/        → Config, session, logging
├── cli.py          → Main CLI
├── cli_llm.py      → LLM runtime controls
```

---

# ✅ Features Completed (Phase 1.0 – 1.5)

## Phase 1.0 – Foundation

* Python package structure
* Typer CLI
* Cross-platform support
* GitHub Actions CI
* platformdirs config + logs

## Phase 1.1 – Core Security & Schema

* Strict Pydantic plan schema
* Policy engine validation
* Session-based JSONL logging
* Append-only audit logs
* SAFE tool execution

## Phase 1.2 – Tool Registry

* Tool registration system
* Risk-level tagging
* Execution lifecycle events:

  * `tool_start`
  * `tool_result`
  * `tool_error`

## Phase 1.3 – LLM Planner Integration

* llama-cpp-python integration
* GGUF model support
* Deterministic JSON-only planning
* JSON extraction layer
* Step ID injection
* allowed_paths injection
* CI-safe fallback

## Phase 1.4 – Model Failover & Abort Safety

* Primary model: Qwen
* Fallback model: Phi
* Silent failover on:

  * Model load failure
  * Timeout
  * Invalid JSON
  * Schema validation failure
* Abort safety (no tool execution on planning failure)
* Structured audit events:

  * `llm_primary_failed`
  * `llm_failover_used`
  * `llm_abort`

## Phase 1.5 – GPU Controls & Benchmarking

* `cortex llm status`
* `cortex llm bench`
* `cortex llm set-gpu-layers`
* GPU layer control
* Auto GPU → CPU fallback
* Portable model path resolution
* RTX 3060 compatible

---

# 🛡 Security Model

Cortex enforces layered safety:

1. Strict JSON planner output
2. Pydantic schema validation
3. Policy engine validation
4. Tool registry restrictions
5. Risk-level tagging
6. Sandbox path enforcement
7. Append-only session logs

No tool executes unless:

* It is registered
* It passes schema validation
* It passes policy validation
* It satisfies risk requirements

---

# ⚡ LLM Runtime

Supported backend:

* `llama-cpp-python`
* GGUF quantized models

Features:

* GPU offloading (`n_gpu_layers`)
* Deterministic mode (temperature 0.0)
* Model failover (Primary → Fallback)
* Timeout enforcement
* Benchmark command

Example:

```bash
cortex llm status
cortex llm bench --runs 5
cortex llm set-gpu-layers 35
```

---

# 🖥 Usage

## Initialize config

```bash
cortex config init
```

## Dry-run (plan only)

```bash
cortex run --dry-run "list current folder"
```

## Execute SAFE tool

```bash
cortex run --execute "list current folder"
```

## Interactive mode

```bash
cortex interactive
```

---

# 📁 Logs

Logs are written to:

```
%LOCALAPPDATA%/cortex/logs/
```

Each session creates:

```
session_<id>.jsonl
```

Events include:

* `session_start`
* `llm_start`
* `llm_success`
* `llm_primary_failed`
* `llm_failover_used`
* `plan_validated`
* `tool_start`
* `tool_result`
* `tool_error`
* `run_result`

Fully auditable and append-only.

---

# 💎 Unique Value Proposition (USP)

| Feature                | Cortex | Typical Agent Framework |
| ---------------------- | ------ | ----------------------- |
| Strict JSON planning   | ✅      | ❌                       |
| Multi-layer validation | ✅      | Partial                 |
| Append-only audit logs | ✅      | Rare                    |
| Local-first design     | ✅      | Often cloud             |
| Model failover         | ✅      | Rare                    |
| GPU runtime control    | ✅      | Limited                 |
| Deterministic mode     | ✅      | Often stochastic        |

Cortex is built as a **secure execution engine**, not a demo agent.

---

# 📦 Installation

```bash
pip install -e .
```

Install llama-cpp:

```bash
pip install llama-cpp-python
```

Place models inside:

```
models/
 ├── qwen.gguf
 └── phi.gguf
```

Update config:

```yaml
llm:
  enabled: true
  primary_model_path: "models/qwen.gguf"
  fallback_model_path: "models/phi.gguf"
```

---

# 🔮 Roadmap

## Phase 1.6 – Risk-Level Enforcement

* SAFE → auto-run
* MODIFY → confirmation required
* CRITICAL → typed YES
* Non-interactive mode
* Approval events logged

## Phase 1.7 – Secure Mode

* Disable non-SAFE tools
* Harden sandbox
* Restricted runtime mode

## Phase 1.8 – Filesystem Expansion

* search
* read_text
* write_text
* move
* size limits

## Phase 1.9 – Desktop UX

* Windows launcher
* Session summaries
* Improved CLI rendering

## Phase 2.0 – Production Release

* Threat model documentation
* Install guide
* Versioning & release packaging

---

# 🧭 Philosophy

Cortex is built on three principles:

1. Determinism over creativity
2. Security over convenience
3. Structure over autonomy

This is execution infrastructure, not experimental AI.

---

# 👨‍💻 Developer

**Akshat Sachdeva**
AI Systems Engineer | RAG Developer

Cortex Engine is an independent systems project focused on building secure, deterministic AI execution infrastructure.

---

# 📜 License

MIT License

---

# ⚖️ Disclaimer

Cortex Engine executes user-defined tasks locally.
The developer is not responsible for misuse, misconfiguration, or unsafe tool extensions.

Always review tools before enabling them in production.

---

# 🏁 Current Version

`v0.1.5`
---