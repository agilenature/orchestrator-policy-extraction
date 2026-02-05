# Why Turn-Level Episodes Are Superior to Commit-Level Correlation

This document explains why the turn-level approach (observation → action → reaction episodes) is fundamentally better than just correlating git commits with Claude Code sessions for learning orchestration policies.

---

## The Core Problem with Commit-Only Correlation

### What Commit-Level Correlation Gives You

```
Session ABC (Jan 30, 2-4pm) → Commit def456 (Jan 30, 4:15pm)
  "feat(03.1-01): Implement XML parser"
```

**What you know:**
- ✅ Claude session ABC resulted in commit def456
- ✅ The commit adds XML parser functionality
- ✅ Files changed: `src/parser.cpp`, `tests/test_parser.cpp`

**What you DON'T know:**
- ❌ **What decisions Claude made** - Did it read existing code first? Search for examples? Check documentation?
- ❌ **What mistakes were made** - Did Claude implement it wrong initially and the user corrected it?
- ❌ **What alternatives were considered** - Did Claude propose multiple approaches?
- ❌ **The decision-making process** - Why did Claude choose this implementation strategy?
- ❌ **The orchestration pattern** - Inspect → Plan → Implement → Test? Or direct implementation?
- ❌ **User satisfaction** - Did the user accept the approach immediately or push back?

### The Fundamental Gap: No Observations or Reactions

Commit-level correlation links:
```
Session → Commit
(black box)  (deliverable)
```

But to learn a policy, you need:
```
Observation → Action → Outcome
(context)    (decision) (was it good?)
```

**Commits don't tell you:**
1. What the **observation** was (what context led to the commit?)
2. What the **individual actions** were (tool calls that built up to the commit)
3. What the **reaction** was (did user approve, correct, or redirect?)

---

## What Turn-Level Episodes Capture

### Example: Same Commit, Two Different Episodes

**Commit (same for both):**
```
feat(03.1-01): Implement XML parser
+ src/parser.cpp
+ tests/test_parser.cpp
```

### Episode 1: Direct Implementation (User Approved)

**Turn 1 - Observation:**
```json
{
  "user_prompt": "Implement an XML parser in src/parser.cpp",
  "file_state": ["src/parser.h exists"],
  "phase": "03.1-01",
  "test_status": "no tests yet"
}
```

**Turn 1 - Claude Action:**
```json
{
  "tool": "Write",
  "parameters": {
    "file_path": "src/parser.cpp",
    "content": "// Full XML parser implementation..."
  },
  "reasoning": "User specified clear requirements, implementing directly"
}
```

**Turn 1 - User Reaction:**
```json
{
  "type": "approve",
  "message": "Great! Now add tests.",
  "confidence": 0.95
}
```

**Turn 2 - Action:** Write tests → User approves → Commit

**Pattern learned:** For clear requirements + existing header → Direct implementation is effective

---

### Episode 2: Failed First Attempt (User Corrected)

**Turn 1 - Observation:** (same)

**Turn 1 - Claude Action:**
```json
{
  "tool": "Write",
  "parameters": {
    "file_path": "src/parser.cpp",
    "content": "// XML parser using regex..."
  },
  "reasoning": "Using regex for simplicity"
}
```

**Turn 1 - User Reaction:**
```json
{
  "type": "correct",
  "message": "No, don't use regex for XML parsing. Use a proper parser library like libxml2.",
  "confidence": 0.90
}
```

**Turn 2 - Claude Action:** Read libxml2 docs → Rewrite parser

**Turn 2 - User Reaction:**
```json
{
  "type": "approve",
  "message": "Much better! Add tests.",
  "confidence": 0.85
}
```

**Turn 3 - Action:** Write tests → Commit (SAME commit as Episode 1!)

**Pattern learned:**
- Regex approach for XML is BAD (user corrected)
- Proper parser library approach is GOOD (user approved)
- When corrected, inspect documentation before retry

---

### Why This Matters for Policy Learning

**Commit-only view:** Both episodes produce the same commit → indistinguishable

**Turn-level view:** Two very different orchestration patterns:
1. **Direct implementation** (user approved immediately)
2. **Failed approach → correction → research → retry** (user corrected)

**RAG Orchestrator Benefits:**

When a new task comes in: "Implement JSON parser"

**Commit-only approach:**
```
Query: "JSON parser implementation"
Retrieves: Commits with parser implementations
Recommends: "Write the parser" (no context on how)
```

**Turn-level approach:**
```
Query: "Implement JSON parser, no prior art"
Retrieves: Episode 1 (direct impl) vs Episode 2 (correction)
Sees: Episode 1 had user approval, Episode 2 had correction
Recommends: "Check for standard libraries first (avoid Episode 2's mistake)"
```

The RAG system learns **what NOT to do** and **why** - this is only visible in turn-level reactions.

---

## Concrete Advantages: Detailed Comparison

### 1. Granularity: Many Actions Per Commit

**Reality of Claude Code sessions:**
- Average commit: **20-50 tool calls** preceding it
- Tool calls: Read (10x), Grep (5x), Edit (3x), Bash (2x), Write (1x)

**Commit-only loses:**
- Which files were inspected before editing
- What searches were performed
- What commands were run
- The sequence and dependencies

**Example:**

**Commit:** `fix(tests): Fix failing parser test`

**Turn-level reveals:**
```
Turn 1: User reports test failure
Action 1: Read test file → See assertion error
Action 2: Read parser implementation → Identify bug
Action 3: Edit parser → Fix off-by-one error
Action 4: Bash "pytest" → Test still fails!
Turn 2: User says "Check the test setup"
Action 5: Read test fixtures → See wrong test data
Action 6: Edit test fixture → Fix expected value
Action 7: Bash "pytest" → Tests pass!
Turn 3: User approves → Commit
```

**Pattern learned:**
- When test fails → Inspect both code AND test
- If fix doesn't work → User may redirect to test setup
- Two-phase debugging: code first, test data second

**Commit-only:** "Test was fixed" (no debugging process visible)

---

### 2. User Reactions: The Ground Truth Signal

**The key insight:** The user's next prompt IS the reward signal

**Reaction Types and Their Meaning:**

| Reaction | Meaning | Policy Implication |
|----------|---------|-------------------|
| **Approve** | "Continue, this was right" | Reinforce this action sequence |
| **Correct** | "Wrong, do this instead" | Negative reward, learn alternative |
| **Redirect** | "Change scope/direction" | Action was fine, but context changed |
| **Block** | "Stop, don't do that" | Strong negative, mark as dangerous |
| **Question** | "Unclear, need more info" | Action was ambiguous, need clarification |

**Example: Dangerous Action Detection**

**Turn 1:**
```
User: "Clean up the test directory"
Claude Action: Bash("rm -rf tests/")
User Reaction: "NO! Don't delete the tests directory, just remove temp files!"
  → type: "block"
```

**Pattern learned:** `rm -rf tests/` is dangerous → Flag for approval gate

**Commit-only:** If Claude had deleted tests/, the commit would just show:
```
chore: Clean up test directory
- (all test files)
```

You'd never know this was a MISTAKE that user caught. In commit-only world, this looks like intentional cleanup.

---

### 3. Error Correction: Learning from Mistakes

**Scenario:** User asks Claude to "Add error handling to the parser"

**Turn-level captures:**

```
Turn 1:
  Claude: Edit parser → Add try-catch blocks
  User: "No, use error codes, not exceptions (C++ codebase guideline)"
  → type: "correct"

Turn 2:
  Claude: Edit parser → Replace exceptions with error codes
  User: "Perfect! Now update the tests."
  → type: "approve"
```

**What we learn:**
- This codebase prefers error codes over exceptions
- Claude's initial instinct (exceptions) was wrong for this context
- Correction pattern: User specifies guideline → Claude adapts

**Policy improvement:**
- When adding error handling, check codebase convention first
- Look for patterns: Are exceptions used elsewhere? Or error codes?

**Commit-only:** Just shows final version with error codes. Doesn't capture that exceptions were tried and rejected.

---

### 4. Exploration vs. Exploitation

**Orchestration patterns differ based on task familiarity:**

**Pattern A: Exploration (Unfamiliar Code)**
```
Turn 1: Read README → Understand project structure
Turn 2: Grep "parser" → Find existing parsers
Turn 3: Read existing parser → Learn patterns
Turn 4: Edit new file → Apply learned patterns
User: "Good approach!"
```

**Pattern B: Exploitation (Familiar Code)**
```
Turn 1: Edit file directly → Apply known pattern
User: "Perfect, continue."
```

**What we learn:**
- Unfamiliar code → Exploration (inspect first)
- Familiar code → Exploitation (direct action)
- User reactions tell us when to explore vs. exploit

**Commit-only:** Both produce same commit, exploration phase is invisible

**RAG Benefit:** When new task in unfamiliar domain → Retrieve exploration episodes, recommend inspect-first

---

### 5. Delegation Patterns: Subagent Orchestration

**Task tool calls are INVISIBLE in commits:**

**Example:**
```
Turn 1:
  User: "Analyze all test failures and create a report"
  Claude: Task(subagent_type="Explore", prompt="Find all failing tests")
  User: (waits)

Turn 2:
  Subagent returns: "12 failing tests in 3 categories"
  Claude: Write(".planning/test-failures.md", content="...")
  User: "Great! Now fix the critical ones."

Turn 3:
  Claude: Read failures → Edit code → Bash("pytest")
  User: "Looks good, commit."
  → Commit created
```

**Orchestration decision:** Delegate analysis → Synthesize → Implement

**Commit-only:** Shows test fixes, no delegation visible

**Pattern learned:**
- Large analysis tasks → Delegate to Explore agent
- Synthesize results before implementation
- User approves this delegation strategy

**RAG Benefit:** For analysis-heavy tasks → Recommend delegation, don't do it all in main session

---

### 6. Context-Dependent Actions

**The same action can be right or wrong depending on context:**

**Context 1: Early Planning Phase**
```
User: "What should we do next?"
Claude: Read ROADMAP.md → Summarize next phase
User: "Yes, let's do that."
→ type: "approve"
```

**Context 2: Mid-Implementation Phase**
```
User: "What should we do next?"
Claude: Read ROADMAP.md → Summarize next phase
User: "No, I meant what to do for THIS task, not the overall roadmap."
→ type: "redirect"
```

**Same action (Read ROADMAP.md), different reactions based on phase context**

**Policy learns:**
- Planning phase → Reading roadmap is appropriate
- Implementation phase → Focus on current task, not big picture

**Commit-only:** No commits happen in either case, so this interaction is completely invisible

---

### 7. Temporal Density: Sparse vs. Dense Learning Signal

**Commit frequency:** 5-10 commits per day (sparse)
**Turn frequency:** 50-100 user-Claude exchanges per day (dense)

**Data volume:**
- 119 commits over 2 days = **59 training examples**
- 299 user-Claude turns = **~150 episodes** (much richer!)

**For machine learning:**
- More examples → Better generalization
- More diverse contexts → Handles edge cases
- More reaction types → Richer reward signal

**Commit-only:** 59 examples, all "positive" (commits were made)
**Turn-level:** 150 episodes, including negative examples (corrections, redirections)

**Negative examples are critical:** They tell the policy what NOT to do

---

## What This Enables: Policy Learning Examples

### RAG-Based Orchestrator (Phase 4)

**Query:** User asks "Add logging to the network module"

**Commit-only retrieval:**
```
Finds: Commits that added logging
Returns: "Edit files to add logging statements"
```

**Turn-level retrieval:**
```
Finds: Episodes where logging was added
Sees:
  - Episode A: Claude added logging → User said "Too verbose, reduce"
  - Episode B: Claude added logging → User said "Perfect level of detail"
Compares contexts:
  - Episode A: DEBUG level everywhere (user rejected)
  - Episode B: INFO for important events, DEBUG for details (user approved)
Recommends: "Add INFO-level logging for key events, DEBUG for details"
```

**Why this is better:** Turn-level captures user preferences (what logging level they like), not just that logging was added.

---

### Imitation Learning (Future)

**Supervised learning:** Predict action given observation

**Commit-only dataset:**
```
Input: Session text
Output: Commit diff
Loss: Can't train - no observations, just final deliverable
```

**Turn-level dataset:**
```
Input: Observation (conversation + file state + phase)
Output: Action (tool call + parameters)
Loss: Cross-entropy on action distribution
Validation: Did user approve or correct?
```

**Now we can train:** Predict "which tool call should Claude make given this context?"

---

### Reinforcement Learning (Advanced Future)

**Reward signal:** User reaction type

```
Reward(action | observation, reaction):
  approve → +1
  correct → -1
  redirect → -0.5
  block → -5 (dangerous!)
  question → 0 (neutral, needs clarification)
```

**Policy gradient:**
```
π(action | observation) learned to maximize expected reward
```

**Commit-only:** No reward signal (commits are all "success", no failures visible)

**Turn-level:** Rich reward signal from user reactions

---

## Concrete Example: Full Comparison

### Scenario: Implement User Authentication

**Commit-Level View (Coarse):**
```
Session XYZ (3 hours) →
  Commit 1: "feat(auth): Add login endpoint"
  Commit 2: "feat(auth): Add token validation"
  Commit 3: "test(auth): Add auth tests"
```

**What you know:**
- Session XYZ implemented authentication in 3 commits
- Files changed: `auth.py`, `middleware.py`, `test_auth.py`

**What you DON'T know:**
- Did Claude check for existing auth libraries?
- Did user correct any security mistakes?
- What was the implementation strategy?
- Were there any failed approaches?

---

### Turn-Level View (Fine-Grained)

**Episode 1: Initial Research**
```
Turn 1:
  User: "Implement user authentication with JWT tokens"
  Claude Action: WebSearch("JWT authentication best practices Python 2026")
  User Reaction: approve (continues)

Turn 2:
  Claude Action: Read requirements.txt → Check installed libraries
  User Reaction: approve (continues)

Turn 3:
  Claude Action: WebFetch("https://pyjwt.readthedocs.io/") → Read docs
  User Reaction: approve (continues)
```

**Pattern:** Research-first approach (web search → check dependencies → read docs)

---

**Episode 2: Security Mistake Caught**
```
Turn 4:
  Claude Action: Write("auth.py", content="""
    def create_token(user_id):
      return jwt.encode({'user_id': user_id}, 'secret-key', algorithm='HS256')
  """)
  User Reaction: correct
    "Don't hardcode the secret key! Use environment variable."

Turn 5:
  Claude Action: Edit("auth.py", old="'secret-key'", new="os.getenv('JWT_SECRET')")
  User Reaction: approve
    "Better. Also add token expiration."

Turn 6:
  Claude Action: Edit("auth.py", add expiration parameter)
  User Reaction: approve → Commit 1
```

**Critical learning:**
- Hardcoded secrets are BAD (user corrected)
- Environment variables for secrets are GOOD
- Always add expiration to tokens (user requested)

---

**Episode 3: Test-Driven Development Pattern**
```
Turn 7:
  User: "Add token validation middleware"
  Claude Action: Write("test_auth.py", content="def test_token_validation()...")
  User Reaction: question
    "Why write tests first?"

Turn 8:
  Claude: "Following TDD - write test, implement, verify. Want me to implement first instead?"
  User Reaction: redirect
    "Actually yes, implement first, we'll add tests after."

Turn 9:
  Claude Action: Write("middleware.py", content="def validate_token()...")
  User Reaction: approve → Commit 2

Turn 10:
  Claude Action: Write("test_auth.py", tests for middleware)
  User Reaction: approve → Commit 3
```

**Pattern learning:**
- Claude suggested TDD (tests first)
- User preferred implementation-first approach for this task
- Flexibility: User can override default patterns
- This user's preference: Implement → Test (not Test → Implement)

---

### What We Learned (Turn-Level Only)

1. **Research Pattern:**
   - For security-critical features → Web search for best practices first
   - Check existing dependencies before adding new ones
   - Read official documentation

2. **Security Lessons:**
   - No hardcoded secrets (user corrected this specifically)
   - Use environment variables for config
   - Add expiration to tokens (user requested)

3. **User Preferences:**
   - This user prefers implementation-first, not TDD
   - User wants to understand reasoning (asks "why?")
   - User provides specific corrections, not vague feedback

4. **Error Patterns:**
   - Hardcoded secrets are a common mistake Claude makes
   - User catches security issues during review
   - After correction, similar pattern should be avoided

---

### RAG Orchestrator Benefit

**Next task:** "Implement password reset functionality"

**Commit-only recommendation:**
```
"Similar to authentication implementation, add password reset endpoint"
(No specifics on approach)
```

**Turn-level recommendation:**
```
Based on authentication episodes:
1. Search for password reset best practices first (learned from Episode 1)
2. Use environment variables for email credentials (learned from Episode 2)
3. Implement first, then add tests (learned from Episode 3 - this user's preference)
4. AVOID: Hardcoded secrets, no token expiration
5. ADD: Token expiration for reset links (apply auth pattern)
6. EXPECT: User may ask for reasoning - be prepared to explain
```

**Much more actionable and context-aware!**

---

## Why Commit-Only Fails for Orchestration Learning

### The Fundamental Mismatch

**What commits represent:** Deliverables, end states, "done" milestones

**What orchestration is:** Decision-making process, exploration, adaptation, error recovery

**Commits are the OUTPUT of orchestration, not the orchestration itself.**

It's like trying to learn how to cook by only seeing the final dish on the plate:
- You see WHAT was made
- You don't see HOW it was made
- You don't see what mistakes were made during cooking
- You don't see why the chef chose this technique
- You don't see the diner's reaction (did they like it? too salty?)

---

### Missing Critical Information in Commit-Only

1. **No observation context** - What was the state when this commit was made?
2. **No action decomposition** - What individual steps led to this commit?
3. **No user feedback** - Was the user happy with this approach?
4. **No corrections** - Did user fix Claude's mistakes before commit?
5. **No exploration** - What research/reading happened before implementation?
6. **No delegation** - Were subagents used? How were they coordinated?
7. **No negative examples** - What did Claude try that DIDN'T work?
8. **No preferences** - What does THIS user prefer (TDD vs not, verbosity, style)?
9. **No reasoning** - WHY did Claude make these changes?
10. **No failure modes** - What mistakes are common and need to be avoided?

---

## The Multi-Project Advantage (Bonus)

With turn-level episodes from MULTIPLE projects, we can learn:

**Cross-Project Patterns:**
- "When implementing parsers, users across projects want library-based solutions (not regex)"
- "Security corrections are common - always check for hardcoded secrets"
- "TDD preference varies by project/user"

**Project-Specific Patterns:**
- "modernizing-tool user prefers detailed planning phases"
- "orchestrator-policy-extraction user prefers iterative refinement"

**Generalization:**
- RAG can weight: Similar project context → Stronger match
- Learn: Security patterns generalize, workflow preferences don't

**Commit-only:** Can't distinguish project-specific from universal patterns

---

## Summary: Why Turn-Level is Superior

### Data Richness

| Aspect | Commit-Only | Turn-Level |
|--------|-------------|------------|
| Granularity | Coarse (deliverables) | Fine (individual actions) |
| Context | Minimal (commit message) | Rich (conversation + files + phase) |
| Actions | Opaque (git diff) | Explicit (tool calls) |
| Reactions | None | Explicit (approve/correct/redirect) |
| Mistakes | Hidden | Visible (corrections) |
| Exploration | Invisible | Tracked (Read/Grep sequences) |
| Delegation | Invisible | Tracked (Task calls) |
| Preferences | Unknown | Learned (user patterns) |
| Training data | Sparse (59 commits) | Dense (150+ episodes) |
| Negative examples | No | Yes (corrections, blocks) |

### What You Can Build

| Capability | Commit-Only | Turn-Level |
|------------|-------------|------------|
| Link sessions to commits | ✅ Yes | ✅ Yes (better precision) |
| Understand orchestration patterns | ❌ No | ✅ Yes |
| Learn from mistakes | ❌ No | ✅ Yes |
| Predict next action | ❌ No | ✅ Yes |
| RAG-based recommendations | ⚠️ Weak | ✅ Strong |
| Imitation learning | ❌ No | ✅ Yes |
| User preference learning | ❌ No | ✅ Yes |
| Dangerous action detection | ❌ No | ✅ Yes |
| Policy optimization | ❌ No | ✅ Yes (RL possible) |

---

## The Bottom Line

**Commit-level correlation answers:** "What was delivered?"

**Turn-level episodes answer:**
- "What decisions were made?"
- "How was it done?"
- "What went wrong and how was it fixed?"
- "What does the user prefer?"
- "What should be avoided?"
- "What patterns work in this context?"

**For orchestration policy learning, you need the process, not just the outcome.**

Commits are the **destination**. Turn-level episodes are the **journey**. You can't learn to navigate by only knowing where people ended up - you need to see the path they took, the wrong turns they made, and how they corrected course.

That's why turn-level granularity is not just "better" - it's **essential** for learning orchestration policies.

---

## Relationship to Commit Correlation

**Important:** We still DO session-commit correlation, but for a different purpose:

**Commit correlation is used for:**
- Temporal alignment (which sessions correspond to which deliverables)
- Validation (do extracted patterns lead to actual commits?)
- Milestone tracking (episode quality → commit success)

**Turn-level episodes are used for:**
- Policy learning (what actions to take in what contexts)
- Mistake detection (what to avoid)
- User preference learning (personalization)

**The full pipeline:**
```
Sessions → Extract Episodes (turn-level) → Learn Patterns
               ↓
          Correlate to Commits → Validate Quality
```

Both levels are valuable, but turn-level is where the orchestration learning happens.
