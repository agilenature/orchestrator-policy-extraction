# Orchestrator Policy Extraction (OPE)

**Learn orchestration policies from Claude Code sessions to enable safe, staged autonomous delegation**

[![Status: In Development](https://img.shields.io/badge/status-in%20development-yellow)](https://github.com/agilenature/orchestrator-policy-extraction)
[![GSD Framework](https://img.shields.io/badge/framework-GSD-blue)](https://gsd.anthropic.com/)

---

## Overview

Orchestrator Policy Extraction (OPE) is a research project that extracts orchestration patterns from Claude Code session traces and git commits. The goal is to learn what makes effective AI-assisted software engineering orchestration, enabling safe delegation to autonomous agents.

**Key Innovation:** Turn-level granularity captures fine-grained decision-making, not just deliverables.

### Vision

```
Claude Code Sessions → Episode Extraction → Policy Learning → Safe Delegation
                ↓                ↓                ↓                ↓
          (obs, action,    Correlation    RAG-based       OpenClaw
           reaction)       Algorithm      Baseline      Staged Promotion
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- Claude Code CLI (for active data collection)
- Access to `~/.claude/projects/` session logs

### Installation

```bash
# Clone this repository
git clone https://github.com/agilenature/orchestrator-policy-extraction.git
cd orchestrator-policy-extraction

# Install dependencies (Phase 1+)
pip install -r requirements.txt

# Verify directory structure
ls data/
# Should see: raw/ processed/ merged/ validation/
```

### Adding Your First Project

See [`docs/guides/INSTRUMENTATION.md`](docs/guides/INSTRUMENTATION.md) for detailed guide. Quick version:

```bash
# 1. Install git hook (optional but recommended)
cd /path/to/your/project
.git/hooks/prepare-commit-msg  # Follow INSTRUMENTATION.md template

# 2. Add project to registry
# Edit data/projects.json or use:
python scripts/add-project.py --name "My Project" --repo "https://github.com/user/repo"

# 3. Process project (Phase 1+)
python scripts/process-project.py --project my-project

# 4. Extract episodes (Phase 2+)
python scripts/extract-episodes.py --project my-project
```

---

## Project Structure

```
orchestrator-policy-extraction/
├── README.md                  # This file - project overview
├── docs/                      # All documentation
│   ├── PROJECT.md            # Problem statement and goals
│   ├── ROADMAP.md            # Detailed phase breakdown
│   ├── design/               # Architecture and design docs
│   ├── guides/               # How-to guides (INSTRUMENTATION, etc.)
│   └── research/             # Original planning documents
├── data/                      # Multi-project dataset
│   ├── projects.json         # Project registry
│   ├── raw/                  # Original sessions + git repos
│   ├── processed/            # Extracted artifacts
│   └── merged/               # Cross-project unified datasets
├── src/                       # Processing pipeline code
│   ├── correlation/          # Session-commit linking
│   ├── extraction/           # Episode extraction
│   ├── taxonomy/             # Action/reaction classification
│   └── orchestrator/         # RAG-based policy
├── scripts/                   # CLI tools
├── analysis/                  # Notebooks and reports
└── .planning/                 # GSD planning artifacts
```

---

## Core Concepts

### Episode = (Observation, Action, Reaction)

```json
{
  "observation": {
    "conversation_context": "Last 3 user/assistant turns",
    "file_state": "Recently read/edited files",
    "phase_label": "Current development phase",
    "test_status": "passing/failing",
    "current_task": "What user asked for"
  },
  "claude_action": {
    "tool": "Read/Edit/Bash/Task/...",
    "parameters": {...},
    "reasoning": "Why Claude chose this action"
  },
  "user_reaction": {
    "type": "approve/correct/redirect/block",
    "message": "User's next prompt",
    "confidence": 0.85
  }
}
```

### Session-Commit Correlation

**Hash-based matching (95%+ precision):**
1. Extract file hashes from session tool calls (Read, Edit, Write)
2. Extract file hashes from git commit diffs
3. Match on hash overlap + temporal proximity
4. High confidence links (>0.9) used for training

**Fallback: Heuristic matching (70-80% precision)** when session IDs not in commits.

### Multi-Project Dataset

**Current Projects:**
1. **modernizing-tool** - C++ modernization with GSD workflow
2. **orchestrator-policy-extraction** (this project) - Meta-learning from our own sessions

**Planned:** 5+ projects covering diverse orchestration patterns

---

## Development Status

**Phase 0: Data Infrastructure Design** (IN PROGRESS)
- ✅ Core documentation created (PROJECT, ROADMAP, INSTRUMENTATION)
- ✅ Directory structure established
- ✅ Design rationale documented (WHY_TURN_LEVEL)
- ✅ Documentation organized in docs/ directory
- ⏳ User approval on architecture
- 🔲 Validation scripts

**Phase 1: Correlation** (NOT STARTED)
**Phase 2: Extraction** (NOT STARTED)
**Phase 3: Taxonomy** (NOT STARTED)
**Phase 4: RAG Baseline** (NOT STARTED)
**Phase 5: Evaluation** (NOT STARTED)

See [docs/ROADMAP.md](docs/ROADMAP.md) for detailed milestones.

---

## Key Documents

- **[docs/](docs/)** - Documentation index (start here!)
- **[docs/PROJECT.md](docs/PROJECT.md)** - Problem statement, goals, success criteria
- **[docs/ROADMAP.md](docs/ROADMAP.md)** - Phase-by-phase implementation plan
- **[docs/design/WHY_TURN_LEVEL.md](docs/design/WHY_TURN_LEVEL.md)** - Why turn-level episodes are superior
- **[docs/guides/INSTRUMENTATION.md](docs/guides/INSTRUMENTATION.md)** - How to add new projects
- **[.planning/PHASE-0-DECISIONS.md](.planning/PHASE-0-DECISIONS.md)** - Architecture decisions
- **[data/README.md](data/README.md)** - Dataset structure and access

---

## Research Questions

1. **What makes effective orchestration?**
   - Which action sequences lead to positive user reactions?
   - How do successful orchestrators balance exploration vs. execution?

2. **Can we predict next actions from context?**
   - RAG baseline: retrieve similar past episodes
   - ML models: learn generalizable policies

3. **What granularity is optimal?**
   - Turn-level (every user prompt) vs. commit-level (deliverables)?
   - Individual tool calls vs. action sequences?

4. **How to safely delegate?**
   - Staged promotion: shadow → read-only → write-in-branch → PR → merge
   - Risk scoring: which actions need approval gates?

---

## Technology Stack

**Data Processing:**
- Python 3.10+ (pandas, jsonlines, GitPython)
- Optional: DuckDB or SQLite for querying

**Policy Learning (Phase 4+):**
- RAG: FAISS or Chroma for episode retrieval
- Optional: sentence-transformers for embeddings
- Optional: scikit-learn for baseline classifiers

**Delegation (Phase 7+):**
- OpenClaw agent framework
- Sandboxing and allowlists
- Approval gate integration

---

## Contributing

**This is currently a single-user research project.** Contributions welcome once Phase 1-2 are complete.

**If you want to help:**
1. Add your own Claude Code project to the dataset (follow [docs/guides/INSTRUMENTATION.md](docs/guides/INSTRUMENTATION.md))
2. Review correlation/extraction code (Phase 1+)
3. Validate action/reaction taxonomies (Phase 3)

---

## Success Metrics

### Phase 1-3 (Data)
- ✅ Correlation precision >90%
- ✅ 500+ episodes across 5+ projects
- ✅ Action taxonomy coverage >90%
- ✅ Reaction categorization accuracy >80%

### Phase 4-5 (Policy)
- ✅ RAG top-3 accuracy >70%
- ✅ Shadow mode agreement >60%
- ✅ Zero dangerous recommendations

### Phase 7+ (Delegation)
- ✅ Autonomous read-only operation (80%+ reliable evidence gathering)
- ✅ Write-in-branch without human intervention
- ✅ PR creation with 90%+ approval rate

---

## Related Work

- **Claude Code** - AI-assisted software engineering CLI
- **OpenClaw** - Agent framework with sandboxing
- **GSD (Get Stuff Done)** - Systematic project execution framework
- **Imitation Learning** - Learning from demonstrations
- **RAG (Retrieval-Augmented Generation)** - Episode-based policy

---

## License

MIT License - see [LICENSE](LICENSE) file for details

---

## Contact

**Project Lead:** David Alfaro
**Repository:** https://github.com/agilenature/orchestrator-policy-extraction

---

## Changelog

**2026-02-05:** Phase 0 initialization
- Created core documentation (PROJECT, ROADMAP, INSTRUMENTATION, WHY_TURN_LEVEL)
- Established directory structure with organized docs/ folder
- Registered initial 2 projects (modernizing-tool, orchestrator-policy-extraction)
- Documented architecture decisions and design rationale

---

## Acknowledgments

Built with [Claude Code](https://claude.com/code) and the [GSD Framework](https://gsd.anthropic.com/).

This project is meta: it learns from its own orchestration sessions!
