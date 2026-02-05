# Instrumentation Guide for Adding Projects to OPE Dataset

This guide explains how to add a new project to the Orchestrator Policy Extraction (OPE) dataset.

**Time to onboard a project:** ~20-30 minutes (after initial setup)

---

## Prerequisites

### 1. Git Hook for Session ID Tracking ✅ ALREADY INSTALLED

**Purpose:** Link commits to Claude Code sessions automatically

**Status:** ✅ **Global git hook is already installed and active!**

A global git hook has been configured that automatically adds session IDs to ALL commits across ALL repositories. You don't need to set up hooks per-project anymore.

**What it does:**
- Automatically detects the current Claude Code session ID
- Adds `X-Claude-Session: {id}` trailer to all commits
- Adds `Co-Authored-By: Claude Sonnet 4.5` attribution
- Works for every repository on your system

**Verification:**

Make any commit and check the message:
```bash
git log -1 --format=%B
```

You should see:
```
Your commit message

X-Claude-Session: d20e0a83-1a4f-4bde-98ae-ef5a3000440f
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**For detailed information:**
See [GLOBAL_GIT_HOOKS.md](GLOBAL_GIT_HOOKS.md) for:
- How the auto-detection works
- Troubleshooting steps
- Manual session ID override
- Customization options

---

### 2. Required Metadata

Before adding a project, collect the following information:

- **Project ID:** Short lowercase identifier (e.g., `modernizing-tool`, `ope`)
- **Project Name:** Human-readable name
- **Description:** One-sentence summary of the project
- **Repository URL:** Git repository URL (GitHub, GitLab, etc.)
- **Commit Range:** Date range or commit SHAs to analyze
- **Session Directory:** Path to Claude Code session logs (e.g., `~/.claude/projects/-Users-david-projects-PROJECT-NAME/`)
- **Session Date Range:** First and last session timestamps
- **Primary Author:** Main developer(s) working on the project

---

## Step-by-Step Onboarding Process

### Step 1: Prepare Project Data

#### 1.1: Export Claude Code Sessions

**Locate session directory:**
```bash
# Claude Code stores sessions in:
ls ~/.claude/projects/

# Find your project (directory name typically matches project path)
# Example: ~/.claude/projects/-Users-david-projects-modernizing-tool/
```

**Verify session completeness:**
```bash
# Count session JSONL files
ls ~/.claude/projects/-Users-david-projects-YOUR-PROJECT/*.jsonl | wc -l

# Check date range
ls -lt ~/.claude/projects/-Users-david-projects-YOUR-PROJECT/*.jsonl | tail -1  # Oldest
ls -lt ~/.claude/projects/-Users-david-projects-YOUR-PROJECT/*.jsonl | head -1  # Newest
```

**Decision: Copy or Reference?**

- **Copy sessions:** If dataset will be shared or backed up separately
  ```bash
  cp -r ~/.claude/projects/-Users-david-projects-YOUR-PROJECT/ \
        /path/to/ope/data/raw/YOUR-PROJECT/sessions/
  ```

- **Reference in place:** If keeping sessions in original location
  ```bash
  # Just record the path in metadata.json (Step 2)
  ```

**Recommendation:** Reference in place initially, copy for archival/sharing later.

#### 1.2: Clone Git Repository

```bash
cd /path/to/ope/data/raw/YOUR-PROJECT/

# Full clone (if you need full history)
git clone <REPO_URL> git/

# OR shallow clone (if only analyzing recent commits)
git clone --shallow-since="2026-01-01" <REPO_URL> git/
```

**Verify commit range:**
```bash
cd git/
git log --oneline --since="2026-02-01" --until="2026-02-06"
```

#### 1.3: Create Project Metadata

**Template:**

Create `data/raw/YOUR-PROJECT/metadata.json`:

```json
{
  "project_id": "your-project",
  "name": "Your Project Name",
  "description": "One-sentence description of what the project does",
  "repository": {
    "url": "https://github.com/username/your-project",
    "branch": "main",
    "commit_range": {
      "start_date": "2026-02-01",
      "end_date": "2026-02-05",
      "start_sha": "abc123...",
      "end_sha": "def456..."
    }
  },
  "sessions": {
    "directory": "/Users/david/.claude/projects/-Users-david-projects-your-project/",
    "date_range": {
      "start": "2026-01-30T10:00:00Z",
      "end": "2026-02-03T18:30:00Z"
    },
    "session_count": 21,
    "subagent_count": 27
  },
  "authors": [
    {
      "name": "Your Name",
      "email": "you@example.com",
      "role": "primary"
    }
  ],
  "data_collection": {
    "date_added": "2026-02-05",
    "added_by": "Your Name",
    "instrumentation": {
      "session_ids_in_commits": true,
      "claude_attribution": true,
      "phase_labels": true
    }
  },
  "quality_metrics": {
    "correlation_precision": null,
    "episode_count": null,
    "action_coverage": null
  }
}
```

**Notes:**
- Leave `quality_metrics` as `null` initially (filled after processing)
- Set `instrumentation.session_ids_in_commits` to `true` if git hook is installed
- `session_count` and `subagent_count` can be approximated initially

---

### Step 2: Add Project to Registry

**Edit `data/projects.json`:**

```bash
cd /path/to/ope/
# If first project, create registry:
echo '{"projects": []}' > data/projects.json

# Add your project (or use script in Step 3)
```

**Manual addition:**
```json
{
  "projects": [
    {
      "id": "your-project",
      "name": "Your Project Name",
      "metadata_path": "data/raw/your-project/metadata.json",
      "status": "pending_processing",
      "added_date": "2026-02-05"
    }
  ]
}
```

---

### Step 3: Run Validation

**Purpose:** Ensure data is complete before processing

```bash
cd /path/to/ope/

# Run validation script (will be created in Phase 0)
python scripts/validate-project.py --project your-project
```

**Expected checks:**
- ✅ Session directory exists and is readable
- ✅ Git repository cloned and accessible
- ✅ metadata.json is valid JSON and complete
- ✅ Session date range overlaps with commit date range
- ✅ At least 5 sessions and 10 commits present
- ✅ Session IDs found in commit messages (if instrumentation enabled)

**If validation fails:**
- Review error messages
- Check file paths and permissions
- Verify date ranges are correct
- Re-run validation after fixes

---

### Step 4: Run Correlation Pipeline

**Automated processing:**

```bash
cd /path/to/ope/

# Process single project (will be created in Phase 1)
python scripts/process-project.py --project your-project

# This will:
# 1. Extract hashes from sessions
# 2. Extract hashes from git commits
# 3. Run correlation algorithm
# 4. Generate session-commit-map.json
# 5. Update quality metrics in metadata.json
```

**Expected outputs:**
- `data/processed/your-project/session-hashes.json`
- `data/processed/your-project/commit-hashes.json`
- `data/processed/your-project/session-commit-map.json`
- `data/processed/your-project/statistics.json`
- Updated `data/raw/your-project/metadata.json` (quality metrics filled)

**Review correlation quality:**
```bash
cat data/processed/your-project/statistics.json
```

Look for:
- `correlation_precision` > 0.9 (excellent)
- `correlation_precision` > 0.7 (acceptable)
- `correlation_precision` < 0.5 (needs investigation)

**If precision is low:**
- Check if session IDs are in commit messages
- Verify session and commit date ranges overlap
- Inspect `session-commit-map.json` for patterns
- Consider manual labeling to improve (Phase 1.4)

---

### Step 5: Extract Episodes

**Run episode extraction:**

```bash
cd /path/to/ope/

# Extract turn-level episodes (will be created in Phase 2)
python scripts/extract-episodes.py --project your-project

# This will:
# 1. Parse session JSONL files
# 2. Build observation features
# 3. Map actions to taxonomy
# 4. Categorize user reactions
# 5. Generate episode dataset
```

**Expected outputs:**
- `data/processed/your-project/episodes/` (one JSONL per session)
- `data/processed/your-project/episode-statistics.json`
- Updated metadata with episode count

**Review episode quality:**
```bash
cat data/processed/your-project/episode-statistics.json
```

Look for:
- `total_episodes` > 50 (good dataset size)
- `observation_completeness` > 0.9 (most features extracted)
- `action_taxonomy_coverage` > 0.9 (most actions classified)

---

### Step 6: Update Cross-Project Indices

**Merge into unified dataset:**

```bash
cd /path/to/ope/

# Regenerate merged indices (will be created in Phase 1/2)
python scripts/merge-datasets.py

# This updates:
# - data/merged/all-correlations.json
# - data/merged/all-episodes.jsonl
# - data/merged/statistics.json
```

**Verify inclusion:**
```bash
# Check project appears in merged dataset
grep "your-project" data/merged/all-episodes.jsonl | wc -l
```

---

### Step 7: Quality Assurance

**Manual spot checks:**

1. **Review a few episodes:**
   ```bash
   head -20 data/processed/your-project/episodes/SESSION_ID.jsonl | jq
   ```
   - Do observations make sense?
   - Are actions correctly categorized?
   - Are reactions plausible?

2. **Check correlation examples:**
   ```bash
   cat data/processed/your-project/session-commit-map.json | jq '.[] | select(.confidence > 0.9) | {commit, session, confidence}' | head -10
   ```
   - Do high-confidence matches look correct?
   - Review commit messages vs. session content

3. **Compare statistics to other projects:**
   ```bash
   cat data/merged/statistics.json | jq '.by_project'
   ```
   - Is your project an outlier? (much lower correlation/episodes?)
   - Investigate if significantly different

**If issues found:**
- Document in `data/raw/your-project/NOTES.md`
- Consider re-processing with adjusted parameters
- May need to exclude low-quality sessions

---

## Troubleshooting

### Session IDs Not in Commits

**Problem:** Git hook wasn't installed or `CLAUDE_SESSION_ID` not set

**Solutions:**
1. **For new commits:** Install hook (see Prerequisites), continue working
2. **For old commits:** Use heuristic correlation (hash + temporal matching)
3. **Manual linking:** Create `session-commit-map-manual.json` with known links

### Low Correlation Precision

**Possible causes:**
- Sessions and commits in different time windows
- Commits made manually (without Claude)
- Sessions with exploration only (no commits)
- Large refactorings (many file changes, hard to match)

**Solutions:**
- Filter to commits with `Co-Authored-By: Claude` (more likely correlated)
- Increase temporal window (e.g., 6 hours instead of 4)
- Manual labeling of 10-20 examples to validate algorithm

### Missing Observation Features

**Problem:** Phase labels, test status not extracted

**Causes:**
- Project doesn't use `.planning/STATE.md` or `.ralph/`
- Different file naming conventions
- Test framework not recognized

**Solutions:**
- Update `observation_builder.py` with project-specific patterns
- Add custom extractors for your project structure
- Document missing features in metadata

### Session Parsing Errors

**Problem:** `session_parser.py` fails on some JSONL files

**Causes:**
- Malformed JSON (session interrupted)
- Unknown tool types (new Claude Code features)
- Subagent nesting issues

**Solutions:**
- Skip malformed sessions (log in `data/processed/PROJECT/parse-errors.log`)
- Update parser to handle new tool types
- Report parsing issues to OPE maintainers

---

## Checklist for Project Onboarding

Use this checklist to ensure nothing is missed:

- [ ] **Prerequisites**
  - [ ] Git hook installed (if applicable)
  - [ ] Session directory located
  - [ ] Repository cloned
  - [ ] Metadata collected

- [ ] **Data Preparation**
  - [ ] Sessions copied or path recorded
  - [ ] Git repository accessible
  - [ ] `metadata.json` created
  - [ ] Project added to `data/projects.json`

- [ ] **Validation**
  - [ ] `validate-project.py` passes all checks
  - [ ] Session/commit date ranges overlap
  - [ ] Minimum data volume (5+ sessions, 10+ commits)

- [ ] **Processing**
  - [ ] `process-project.py` completed successfully
  - [ ] Correlation precision > 0.7 (or documented if lower)
  - [ ] `extract-episodes.py` completed successfully
  - [ ] Episode count > 50 (or documented if lower)

- [ ] **Integration**
  - [ ] Merged indices updated
  - [ ] Project appears in `all-episodes.jsonl`
  - [ ] Statistics added to `data/merged/statistics.json`

- [ ] **Quality Assurance**
  - [ ] Spot-checked 5+ episodes (look reasonable)
  - [ ] Reviewed 3+ high-confidence correlations (correct)
  - [ ] Compared statistics to other projects (no major outliers)
  - [ ] Documented any issues in `NOTES.md`

- [ ] **Documentation**
  - [ ] Updated `README.md` in project directory (if needed)
  - [ ] Added project to OPE's main README (projects list)
  - [ ] Noted any special considerations or limitations

---

## Future Automation

**Phase 6 will add:**
- `scripts/add-project.py` - Interactive CLI wizard for all above steps
- `scripts/update-project.py` - Incremental processing for new sessions/commits
- GitHub Actions / cron jobs for periodic updates

**Until then:** Follow this manual process. Expected time: 20-30 minutes per project after initial setup.

---

## Getting Help

**If you encounter issues:**
1. Check troubleshooting section above
2. Review `data/processed/PROJECT/parse-errors.log` or similar logs
3. Compare your project structure to `modernizing-tool` (reference example)
4. Open an issue on the OPE repository with:
   - Project metadata
   - Error messages / logs
   - Correlation/episode statistics

**For questions about:**
- Claude Code session format → Claude Code documentation
- Git hooks → Git documentation (`man githooks`)
- OPE-specific issues → This project's issue tracker
