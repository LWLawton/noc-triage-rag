# NOC Pre-Triage AI Assistant

A secure, local, read-only AI-powered pre-triage agent for Cisco network tickets.

Runs **after** a monitoring system generates a ticket and **before** it is assigned to a human engineer. Performs read-only Cisco health checks, retrieves relevant runbooks from a local RAG index, and generates a structured triage note — all without any internet access, external APIs, or configuration changes.

---

## Security Model

| Guarantee | How it is enforced |
|---|---|
| No config changes | Command broker allow-list + deny-list |
| No credentials in prompts or logs | Sanitization layer in `safety.py` + `llm_client.py` |
| No external API calls | Ollama runs locally; Chroma runs locally |
| No internet access | No external HTTP calls in any module |
| Device scope enforced | `device_scope.yaml` validated before every command |
| Full audit trail | `logs/audit.jsonl` — structured JSON lines, SIEM-ready |
| Rate limiting | Per-device sliding window + hard per-ticket command cap |
| Credentials via Vault (Phase 2) | `SecretsProvider` interface pre-stubbed in `command_broker.py` |

---

## Architecture

```
Ticket JSON
    │
    ▼
app.py ──► TicketClient (load + validate)
    │
    ├──► SafetyValidator (device scope check)
    │
    ├──► CommandBroker ──► SafetyValidator (allow/deny-list)
    │         │                    │
    │         │            cisco_health_checks.py (mock or Netmiko)
    │         │
    │         └──► sanitized outputs
    │
    ├──► RAGSearch (Chroma + sentence-transformers)
    │         └──► runbook context
    │
    ├──► LLMClient (Ollama / template fallback)
    │         └──► triage note
    │
    ├──► TicketClient (save note to outputs/)
    └──► AuditLogger (write audit.jsonl)
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Required |
| Ollama | Install from https://ollama.com/download |
| llama3.1 model | `ollama pull llama3.1` |
| ~4 GB RAM (for LLM) | Less if using `--no-llm` flag |
| ~500 MB disk (for embeddings) | `all-MiniLM-L6-v2` downloads on first run |

---

## Quick Start

### 1. Clone / copy the project

```bash
cd noc_triage_agent/
```

### 2. Create a virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate       # Linux/macOS
venv\Scripts\activate          # Windows
```

### 3. Install dependencies

**Core + RAG (recommended):**
```bash
pip install -r requirements.txt
```

**Core only (no RAG, no live mode):**
```bash
pip install pydantic pyyaml requests
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env if you want to change Ollama model or paths
```

### 5. Start Ollama

```bash
# In a separate terminal:
ollama serve

# Pull the model (first time only):
ollama pull llama3.1
```

### 6. Run the agent (mock mode)

```bash
python app.py --ticket tickets/sample_ticket_interface_down.json --mock
```

### 7. Run without LLM (template mode only)

```bash
python app.py --ticket tickets/sample_ticket_interface_down.json --mock --no-llm
```

### 8. Force rebuild the RAG index

```bash
python app.py --ticket tickets/sample_ticket_interface_down.json --mock --rebuild-index
```

---

## Expected Output

```
============================================================
  NOC AI Pre-Triage Agent
  Read-only analysis. No changes made.
============================================================

[1/9] Loading configuration...
[2/9] Loading ticket from: tickets/sample_ticket_interface_down.json
       Ticket ID: INC12345 | Alert: Interface Down | Device: access-sw-22
[3/9] Classifying ticket type...
       Type: interface_down
[4/9] Validating device scope...
       Device 'access-sw-22' is approved (tier=access)
[5/9] Running health checks [MOCK mode]...
       Commands executed: 10
[6/9] Retrieving runbook from local RAG...
       Retrieved: interface_down.md
[7/9] Generating triage note...
       [LLM: llama3.1]
[8/9] Saving triage note...
       Saved: outputs/triage_note_INC12345.txt
[9/9] Complete.

============================================================
TRIAGE NOTE
============================================================

AI Pre-Triage Findings
======================
...

============================================================

Full note saved to: outputs/triage_note_INC12345.txt
Audit log saved to: logs/audit.jsonl
```

---

## Testing in a Closed / Air-Gapped Environment

This project is designed to be **fully testable with zero internet access and zero real network devices**. The sections below cover every testing tier from core unit tests to a full end-to-end run.

---

### Tier 1 — Core Unit Tests (No internet, no LLM, no RAG required)

These tests cover safety validation, command broker enforcement, and ticket schema. They only need `pydantic`, `pyyaml`, and `pytest` — all installable from a local PyPI mirror or pre-downloaded wheels.

```bash
# Install minimal dependencies
pip install pydantic pyyaml requests pytest

# Run core tests
pytest tests/test_safety.py tests/test_ticket_schema.py tests/test_command_broker.py -v
```

**Expected result: 110 tests, 110 passed.**

What is being tested:
- Every forbidden command (configure, reload, write, debug, shutdown, etc.) is blocked
- Every allowed command template passes with valid parameters
- Interface name injection attempts are rejected (`../../etc`, `Gi1/0/$(id)`)
- IP address validation (multicast blocked, loopback blocked, invalid strings rejected)
- VLAN range enforcement (0 and 4095+ rejected)
- Device scope enforcement (core routers, firewalls, unknown devices all blocked)
- Hard per-ticket command limit
- Rate limiting per device
- Ticket ID path traversal prevention
- Pydantic schema validation for all ticket fields

---

### Tier 2 — RAG Tests (No internet, no LLM, no real devices required)

Requires `chromadb` and `sentence-transformers`. On first run, `all-MiniLM-L6-v2` (~90 MB) is downloaded from HuggingFace. In a truly air-gapped environment, pre-download the model and set `SENTENCE_TRANSFORMERS_HOME` to point to the local cache.

```bash
# Install RAG dependencies
pip install chromadb sentence-transformers

# Run RAG tests (uses a temporary Chroma DB — no persistent state)
pytest tests/test_rag_search.py -v
```

**Air-gapped pre-download (run this once on an internet-connected machine):**
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
# Model saved to ~/.cache/huggingface/hub/
# Copy that cache directory to your air-gapped machine
```

**On air-gapped machine:**
```bash
export SENTENCE_TRANSFORMERS_HOME=/path/to/your/local/model/cache
pytest tests/test_rag_search.py -v
```

---

### Tier 3 — Full End-to-End Run (Mock mode, no real devices, no internet)

This is the primary closed-environment validation. Runs the complete triage workflow using mocked Cisco outputs. Does NOT require Ollama or any network connectivity.

```bash
# Run with template fallback (no Ollama needed)
python app.py --ticket tickets/sample_ticket_interface_down.json --mock --no-llm
```

**Expected result:**
- 10 health checks executed (show version, show clock, show interface, show interface status, show interface counters errors, show running-config interface, show logging, show cdp neighbors, show power inline, show mac address-table)
- 0 commands blocked
- Triage note saved to `outputs/triage_note_INC12345.txt`
- Audit log written to `logs/audit.jsonl`
- Full note printed to terminal

**Verify the audit log:**
```bash
python3 -c "
import json
with open('logs/audit.jsonl') as f:
    for line in f:
        rec = json.loads(line)
        print(f\"{rec['event_type']:30s} | {rec.get('command', rec.get('message', ''))[:50]}\")
"
```

---

### Tier 4 — End-to-End with Local LLM (Ollama, no internet after model pull)

Requires Ollama installed locally. The model only needs to be pulled once; after that it runs fully offline.

```bash
# Step 1: Install Ollama (https://ollama.com/download)
# Step 2: Pull the model (requires internet — one time only)
ollama pull llama3.1

# Step 3: Start Ollama server
ollama serve   # run in a separate terminal

# Step 4: Run the full pipeline
python app.py --ticket tickets/sample_ticket_interface_down.json --mock
```

**Air-gapped Ollama setup:** Ollama stores models in `~/.ollama/models/`. Pull the model on an internet-connected machine, copy the `~/.ollama/` directory to your air-gapped machine, and run `ollama serve` normally.

---

### Run All Tests with Coverage

```bash
pip install pytest pytest-cov
pytest tests/ -v --cov=tools --cov-report=term-missing
```

---

### Test What Each File Controls

| Test file | What it validates |
|---|---|
| `test_safety.py` | Allow-list, deny-list, interface/IP/VLAN validation, output sanitization, device scope |
| `test_command_broker.py` | End-to-end command execution gating, rate limiting, hard limits, device scope via broker |
| `test_ticket_schema.py` | Pydantic v2 schema, field validation, path traversal prevention, file I/O |
| `test_rag_search.py` | Chroma indexing, semantic search accuracy, direct runbook retrieval, context formatting |

---

### Confirming No Network Calls Are Made

To verify the application makes zero external network calls during mock mode:

```bash
# Linux: use strace to monitor syscalls
strace -e trace=network -f python app.py \
  --ticket tickets/sample_ticket_interface_down.json \
  --mock --no-llm 2>&1 | grep -v "^strace" | grep "connect\|socket" || echo "No external connections detected"

# Or use a network namespace (fully isolated):
unshare --net python app.py \
  --ticket tickets/sample_ticket_interface_down.json \
  --mock --no-llm
# If it runs successfully, it needed zero network access.
```

---

## Project Structure

```
noc_triage_agent/
├── app.py                          # Main orchestration entry point
├── requirements.txt
├── README.md
├── .env.example                    # Environment variable template
│
├── config/
│   ├── allowed_commands.yaml       # Command allow-list
│   ├── device_scope.yaml           # Approved device inventory
│   ├── ticket_types.yaml           # Alert → health check mapping
│   └── safety_policy.yaml          # Global safety rules
│
├── tickets/
│   └── sample_ticket_interface_down.json
│
├── runbooks/                       # Markdown troubleshooting guides
│   ├── interface_down.md
│   ├── bgp_neighbor_down.md
│   ├── ospf_neighbor_down.md
│   ├── high_cpu.md
│   ├── switch_stack_issue.md
│   ├── vlan_issue.md
│   ├── stp_issue.md
│   ├── hsrp_issue.md
│   └── wireless_ap_down.md
│
├── tools/
│   ├── audit_logger.py             # Structured JSON-lines audit log
│   ├── safety.py                   # All validation logic
│   ├── command_broker.py           # Single command execution choke point
│   ├── cisco_health_checks.py      # Health check sets + mock outputs
│   ├── rag_search.py               # Chroma RAG retrieval
│   ├── llm_client.py               # Ollama client + template fallback
│   └── ticket_client.py            # Ticket loader + output writer
│
├── outputs/                        # Generated triage notes
├── logs/                           # audit.jsonl written here
├── chroma_db/                      # Chroma persistent vector store
│
└── tests/
    ├── test_command_broker.py
    ├── test_safety.py
    ├── test_rag_search.py
    └── test_ticket_schema.py
```

---

## Adding a New Runbook

1. Create `runbooks/your_topic.md` following the existing format
2. Add an entry to `config/ticket_types.yaml` with aliases and health checks
3. Run `python app.py --ticket ... --mock --rebuild-index` to re-index

---

## Adding a New Device

Edit `config/device_scope.yaml` and add the device under the appropriate group:

```yaml
  access_switches:
    tier: access
    allowed_in_triage: true
    devices:
      - hostname: "your-new-switch"
        site: "YourSite"
        platform: "ios"
```

---

## Phase 2 Roadmap

| Feature | Status |
|---|---|
| Live Netmiko device connections | Stubbed in `command_broker.py` |
| HashiCorp Vault credential provider | Interface pre-defined; `hvac` in requirements |
| ServiceNow ticket update | Stub in `ticket_client.py` |
| NX-OS platform support | Mock outputs ready; Netmiko adapter needed |
| NAPALM adapter | In requirements; wire-up in `command_broker.py` |
| Multi-device triage (uplink tracing) | Planned |
| Web UI / dashboard | Planned |

---

## Important Disclaimers

- This tool performs **read-only** checks only. No configuration changes, reloads, restarts, or port bounces are performed under any circumstances.
- All triage findings are preliminary. A qualified network engineer must review and verify all findings before taking any action.
- This tool is intended for internal NOC use only and should never be exposed to untrusted networks or users.
- Credentials must never appear in ticket notes, logs, LLM prompts, or terminal output.
