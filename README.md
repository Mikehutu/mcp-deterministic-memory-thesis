# MCP Deterministic Memory – Thesis PoC

> A proof-of-concept demonstrating Model Context Protocol (MCP) with a deterministic Neo4j memory layer for AI agents, using Statistics Finland open data.

**Tämä repositorio on liite TAMK:n YAMK-opinnäytetyöhön (2026).**

---

## Thesis

**Title:** Model Context Protocol (MCP) and Deterministic Memory: Opportunities for Utilizing Structured Data in AI Development

**Institution:** Tampere University of Applied Sciences (TAMK), Master's Degree Programme  
**Year:** 2026  
**Thesis PDF:** [Link to be added after publication]  
**URN:** [URN to be added after publication]

### Abstract

This thesis investigates the use of Model Context Protocol (MCP) as an integration layer between large language models (LLMs) and external structured data sources. The central hypothesis is that for precise, numerical structured data, a deterministic retrieval approach — using direct Cypher queries against a Neo4j graph database — outperforms semantic memory systems (Mem0, Graphiti by Zep) and pure vector-based retrieval (Basic RAG) in accuracy, cost, and latency.

The proof-of-concept connects two MCP servers to a Claude LLM: one server fetches live data from Statistics Finland's PxWeb API, and the other provides a deterministic memory layer backed by Neo4j. A benchmark was conducted comparing four memory systems on 340 data points across 10 Finnish municipalities and 5 years (2020–2024).

Results show that deterministic memory achieved 98.6% exact match accuracy at $0.00 cost per query and ~4 ms latency, while semantic systems achieved 0–80% accuracy at considerably higher cost and latency. The thesis concludes that for structured statistical and factual data, deterministic retrieval is both technically superior and practically more feasible.

---

## System Overview

```
┌──────────────────────────────────────────────────────────┐
│                   LLM (Claude / GPT)                     │
│               ═══ SEMANTIC LAYER ═══                     │
│  Understands user intent, calls appropriate MCP tools    │
└──────────────────┬───────────────────┬───────────────────┘
                   │ MCP               │ MCP
                   ▼                   ▼
     ┌─────────────────────┐   ┌─────────────────────┐
     │   StatFin Server    │   │   Memory Server     │
     │  📊 Live API Data   │   │  🧠 Stored Facts    │
     └──────────┬──────────┘   └──────────┬──────────┘
                │ HTTPS                   │ Bolt
                ▼                         ▼
     ┌─────────────────────┐   ┌─────────────────────┐
     │  Statistics Finland │   │       Neo4j         │
     │    PxWeb API        │   │  (Cypher Queries)   │
     └─────────────────────┘   └─────────────────────┘
```

**Key insight:** The LLM acts as the semantic layer. The Memory Server is a pure, deterministic, fast data store — no embeddings, no hallucination risk.

---

## System Requirements

| Component     | Version     | Notes                        |
|---------------|-------------|------------------------------|
| Python        | ≥ 3.11      | Tested on 3.11 and 3.12      |
| Docker        | ≥ 24.0      | Docker Compose v2 required   |
| Neo4j         | 5.26.0      | Community Edition sufficient |
| OpenAI API    | Optional    | Only needed for Mem0/Graphiti comparison benchmarks |

Hardware: 8 GB RAM minimum (16 GB recommended for full benchmark with all 4 systems).

---

## Quick Start

### 1. Clone and configure

```bash
git clone <repository-url>
cd thesis-poc

# Copy environment template and fill in values
cp .env.example .env
# Edit .env — set at minimum NEO4J_PASSWORD
```

### 2. Start infrastructure

```bash
docker compose up -d neo4j
# Wait ~30 seconds for Neo4j to be ready
docker compose ps   # confirm neo4j is healthy
```

### 3. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 4. Run the StatFin MCP Server

```bash
python -m statfin_server.server
```

In a separate terminal:

### 5. Run the Memory MCP Server

```bash
python -m memory_server.server
```

### 6. Connect with an MCP-compatible LLM client

Add the servers to your Claude Desktop or other MCP client configuration:

```json
{
  "mcpServers": {
    "statfin-tool": {
      "command": "python",
      "args": ["-m", "statfin_server.server"],
      "cwd": "/path/to/thesis-poc"
    },
    "memory-brain": {
      "command": "python",
      "args": ["-m", "memory_server.server"],
      "cwd": "/path/to/thesis-poc"
    }
  }
}
```

### 7. (Optional) Run the full benchmark

```bash
# Start all containers (Neo4j, Qdrant, Neo4j-Graphiti)
docker compose up -d

# Set OPENAI_API_KEY in .env for Mem0 and Graphiti benchmarks
python benchmark/comparative_benchmark.py --expanded

# Deterministic system only (no API key needed)
python benchmark/comparative_benchmark.py --expanded --systems deterministic
```

See [benchmark/README.md](benchmark/README.md) for full reproduction instructions.

---

## Project Structure

```
thesis-poc/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── docker-compose.yml
├── requirements.txt
├── EXCLUDED_FILES.md
│
├── statfin_server/        # MCP server — Statistics Finland PxWeb API
│   ├── server.py            # MCP tool definitions (FastMCP)
│   ├── client.py            # PxWeb HTTP client
│   └── README.md
│
├── memory_server/         # MCP server — Deterministic Neo4j memory
│   ├── server.py            # MCP tool definitions (11 tools)
│   ├── graphiti_client.py   # Neo4j client (no embeddings)
│   ├── models.py            # Pydantic data schemas
│   ├── extractors/          # Data extraction pipeline
│   └── README.md
│
├── benchmark/             # Complete comparative evaluation
│   ├── comparative_benchmark.py   # Runs all 4 memory systems
│   ├── fetch_expanded_data.py     # Fetches live StatFin data
│   ├── generate_visualizations.py # Generates figures
│   ├── benchmark_data_expanded.json  # Input dataset (340 points)
│   ├── ground_truth_expanded.json    # 355 ground truth queries
│   ├── benchmark_config.md          # System parameters
│   └── results/
│       ├── benchmark_results_expanded.json   # Main results
│       ├── benchmark_results_mem0_fixed.json # Mem0 corrected run
│       ├── benchmark_results_mem0.json       # Mem0 initial run
│       ├── benchmark_results_test.json       # Test run
│       └── results_summary.md               # Human-readable summary
│
├── scripts/               # Utility scripts
│   ├── setup_neo4j.py       # Initialize Neo4j indices (Graphiti)
│   └── clear_neo4j.py       # Wipe Neo4j database
│
└── docs/
    ├── architecture.md          # System design documentation
    ├── neo4j-schema.md          # Graph database schema
    ├── mcp-tools-spec.md        # Full MCP tool specifications
    ├── ai-usage.md              # AI tool usage disclosure
    ├── EVALUATION_REPORT.md     # Full thesis evaluation report
    ├── graphrag_exclusion_rationale.md  # Why GraphRAG was excluded
    └── figures/                 # Publication-quality charts (PNG + SVG)
        ├── accuracy_comparison.*
        ├── latency_comparison.*
        ├── cost_comparison.*
        ├── performance_radar.*
        └── summary_table.*
```

---

## License

MIT — see [LICENSE](LICENSE).

## Citation

If you use this code or benchmark data in your own research, please cite:

```
[Author Name]. (2026). MCP Deterministic Memory – Thesis PoC.
Master's Thesis, Tampere University of Applied Sciences.
GitHub: <repository-url>
```

BibTeX:

```bibtex
@mastersthesis{author2026mcp,
  author  = {[Author Name]},
  title   = {Model Context Protocol (MCP) and Deterministic Memory:
             Opportunities for Utilizing Structured Data in AI Development},
  school  = {Tampere University of Applied Sciences (TAMK)},
  year    = {2026},
  url     = {[URN/URL after publication]}
}
```
