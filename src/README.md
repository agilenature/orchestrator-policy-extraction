# Source Code Directory

This directory contains the data processing pipeline and orchestrator implementation.

## Structure

```
src/
├── correlation/       # Session-commit correlation (Phase 1)
├── extraction/        # Episode extraction (Phase 2)
├── taxonomy/          # Action/reaction classification (Phase 3)
└── orchestrator/      # RAG-based policy (Phase 4)
```

## Modules

### `correlation/` (Phase 1)

**Purpose:** Link Claude Code sessions to git commits

**Files (to be created):**
- `hash_extractor.py` - Extract file hashes from session tool calls
- `git_hash_extractor.py` - Extract hashes from commit diffs
- `correlator.py` - Match sessions to commits with confidence scoring
- `utils.py` - Shared utilities

**Key Functions:**
- `extract_session_hashes(session_jsonl_path) -> Dict[str, List[Tuple[filepath, hash]]]`
- `extract_commit_hashes(git_repo_path) -> Dict[sha, CommitHashes]`
- `correlate(session_hashes, commit_hashes, threshold=0.6) -> SessionCommitMap`

---

### `extraction/` (Phase 2)

**Purpose:** Parse sessions into turn-level episodes

**Files (to be created):**
- `session_parser.py` - Parse JSONL logs into structured turns
- `observation_builder.py` - Extract observation features
- `action_mapper.py` - Map tool calls to action taxonomy
- `reaction_categorizer.py` - Classify user reactions
- `episode_builder.py` - Combine into complete episodes

**Key Functions:**
- `parse_session(jsonl_path) -> List[Turn]`
- `build_observation(turn, context) -> Observation`
- `map_action(tool_call, taxonomy) -> ActionLabel`
- `categorize_reaction(user_message, taxonomy) -> ReactionType`

---

### `taxonomy/` (Phase 3)

**Purpose:** Define and refine action/reaction classifications

**Files (to be created):**
- `action_taxonomy.py` - Load and validate action taxonomy
- `reaction_taxonomy.py` - Load and validate reaction taxonomy
- `reaction_classifier.py` - Train automated reaction categorizer
- `validator.py` - Inter-rater agreement and validation

**Key Functions:**
- `load_action_taxonomy() -> ActionTaxonomy`
- `load_reaction_taxonomy() -> ReactionTaxonomy`
- `train_reaction_classifier(labeled_data) -> Classifier`
- `validate_taxonomy(episodes, gold_labels) -> ValidationReport`

---

### `orchestrator/` (Phase 4)

**Purpose:** RAG-based baseline orchestrator for action recommendation

**Files (to be created):**
- `episode_indexer.py` - Index episodes for retrieval
- `rag_policy.py` - Retrieve similar episodes and recommend actions
- `explainer.py` - Generate explanations for recommendations
- `shadow_mode.py` - Framework for testing on new sessions

**Key Functions:**
- `index_episodes(episodes) -> EpisodeIndex`
- `recommend_action(observation, index, k=10) -> List[Action]`
- `explain_recommendation(action, retrieved_episodes) -> Explanation`
- `run_shadow_mode(session, policy) -> ShadowModeReport`

---

## Development Guidelines

### Code Style
- **Formatting:** Black (line length 100)
- **Type hints:** Required for all public functions
- **Docstrings:** Google style
- **Linting:** Ruff

### Testing
- Unit tests in `tests/` (mirrors src/ structure)
- Integration tests for full pipeline
- Validation sets in `data/validation/`

### Error Handling
- Graceful degradation (log errors, continue processing)
- Validation at module boundaries
- Clear error messages with context

### Logging
- Use Python `logging` module
- Levels: DEBUG (verbose), INFO (progress), WARNING (issues), ERROR (failures)
- Log to `data/processed/PROJECT/processing.log`

---

## Dependencies

**Core (all phases):**
```
python>=3.10
jsonlines
GitPython
tqdm
```

**Phase 1 (correlation):**
```
numpy
scipy
```

**Phase 2 (extraction):**
```
pandas
dateutil
```

**Phase 3 (taxonomy):**
```
scikit-learn
nltk  # for keyword extraction
```

**Phase 4 (orchestrator):**
```
faiss-cpu  # or faiss-gpu
sentence-transformers  # optional, for embeddings
```

**Development:**
```
pytest
black
ruff
mypy
```

---

## Usage Examples

### Phase 1: Correlation

```python
from src.correlation import hash_extractor, git_hash_extractor, correlator

# Extract hashes from session
session_hashes = hash_extractor.extract_session_hashes(
    "data/raw/modernizing-tool/sessions/abc123.jsonl"
)

# Extract hashes from git
commit_hashes = git_hash_extractor.extract_commit_hashes(
    "data/raw/modernizing-tool/git/"
)

# Correlate
mapping = correlator.correlate(
    session_hashes, commit_hashes, threshold=0.7
)

# Save results
mapping.save("data/processed/modernizing-tool/session-commit-map.json")
```

### Phase 2: Extraction

```python
from src.extraction import session_parser, episode_builder

# Parse session
turns = session_parser.parse_session(
    "data/raw/modernizing-tool/sessions/abc123.jsonl"
)

# Build episodes
episodes = episode_builder.build_episodes(
    turns,
    action_taxonomy="data/action-taxonomy.json",
    reaction_taxonomy="data/reaction-taxonomy.json"
)

# Save
episode_builder.save_episodes(
    episodes,
    "data/processed/modernizing-tool/episodes/abc123.jsonl"
)
```

### Phase 4: Orchestrator

```python
from src.orchestrator import episode_indexer, rag_policy

# Load episodes
episodes = load_all_episodes("data/merged/all-episodes.jsonl")

# Index
index = episode_indexer.index_episodes(episodes)

# Get recommendation
observation = current_observation()  # From new session
recommendations = rag_policy.recommend_action(
    observation, index, k=10
)

# Explain
for action in recommendations[:3]:
    explanation = rag_policy.explain_recommendation(action)
    print(f"{action}: {explanation}")
```

---

## Performance Considerations

### Phase 1: Correlation
- **Bottleneck:** Git object database queries
- **Optimization:** Cache blob hashes, use git-cat-file batch mode
- **Expected time:** ~30 seconds per 100 commits

### Phase 2: Extraction
- **Bottleneck:** Session parsing (large JSONL files)
- **Optimization:** Stream processing, parallel session processing
- **Expected time:** ~1 minute per 50 MB session log

### Phase 4: Retrieval
- **Bottleneck:** Episode similarity search
- **Optimization:** FAISS indexing, pre-compute embeddings
- **Expected time:** <100ms per query with FAISS

---

## Current Status

- ✅ Directory structure created
- ✅ Module plan documented
- 🔲 Implementation (starts in Phase 1)

---

## Next Steps

1. Phase 1.2: Implement `hash_extractor.py`
2. Phase 1.3: Implement `git_hash_extractor.py`
3. Phase 1.4: Implement `correlator.py`
4. Phase 2.1: Implement `session_parser.py`
5. ... (See ROADMAP.md for full sequence)
