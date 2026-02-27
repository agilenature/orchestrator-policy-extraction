"""3-tier CCD axis extraction engine for documentation indexing.

Indexes the docs/ corpus into the doc_index DuckDB table with CCD axis
associations extracted via a 3-tier cascade:

  Tier 1 (frontmatter):  YAML ``axes:`` key in frontmatter  -> conf=1.0
  Tier 2 (regex):        H1/H2 headers or HTML CCD comments -> conf=0.7
  Tier 3 (keyword):      Token frequency matching            -> conf=0.4

Documents with no axis match receive ``ccd_axis='unclassified'`` at conf=0.0.

Safety: ``reindex_docs`` aborts if the governance bus daemon is reachable
(write-path must not conflict with live bus DuckDB writes).
"""

from __future__ import annotations

import hashlib
import re
import socket as socket_mod
import sys
from pathlib import Path
from typing import Any

import duckdb
import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER3_STOPWORDS = frozenset(
    {"not", "vs", "as", "to", "the", "a", "an", "in", "of", "for", "is"}
)

DEFAULT_BUS_SOCKET = "/tmp/ope-governance-bus.sock"

_MEMORY_MD_AXIS_RE = re.compile(r"\*\*CCD axis:\*\*\s+`([^`]+)`")

# ---------------------------------------------------------------------------
# 1. Axis vocabulary loader
# ---------------------------------------------------------------------------


def load_axis_vocabulary(
    db_path: str = "data/ope.db",
    memory_md_path: str | None = None,
) -> list[str]:
    """Load known CCD axes from DuckDB (primary) or MEMORY.md (fallback).

    Always includes ``'always-show'`` (a doc_index-only concept).
    Returns a sorted, deduplicated list.  Fails gracefully on any error.
    """
    axes: set[str] = set()

    # Primary: DuckDB memory_candidates
    try:
        conn = duckdb.connect(db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT DISTINCT ccd_axis FROM memory_candidates "
                "WHERE LENGTH(TRIM(ccd_axis)) > 0"
            ).fetchall()
            axes.update(r[0] for r in rows if r[0])
        finally:
            conn.close()
    except Exception:
        pass

    # Fallback: parse MEMORY.md if DB gave nothing
    if not axes:
        if memory_md_path is None:
            memory_md_path = str(
                Path.home()
                / ".claude"
                / "projects"
                / "-Users-david-projects-orchestrator-policy-extraction"
                / "memory"
                / "MEMORY.md"
            )
        try:
            content = Path(memory_md_path).read_text()
            axes.update(_MEMORY_MD_AXIS_RE.findall(content))
        except Exception:
            pass

    # Always include 'always-show' (doc_index-only concept)
    axes.add("always-show")

    return sorted(axes)


# ---------------------------------------------------------------------------
# 2. Tier 1 -- Frontmatter axes
# ---------------------------------------------------------------------------


def _parse_frontmatter_axes(content: str) -> list[str]:
    """Extract ``axes`` from YAML frontmatter.

    CRITICAL (Pitfall 4): Frontmatter MUST start on line 0 with exactly
    ``---``.  Files starting with ``#`` or any other content have NO
    frontmatter.
    """
    lines = content.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return []

    # Find closing ---
    closing_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        return []

    yaml_block = "\n".join(lines[1:closing_idx])
    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return []

    if not isinstance(parsed, dict):
        return []

    axes = parsed.get("axes")
    if axes is None:
        return []
    if isinstance(axes, list):
        return [str(a) for a in axes]
    return []


# ---------------------------------------------------------------------------
# 3. Tier 2 -- Headers / HTML comments
# ---------------------------------------------------------------------------


def _axis_in_headers_or_comments(content: str, axis: str) -> bool:
    """Check if *axis* appears in H1/H2 headers or ``<!-- ccd: axis -->`` comments."""
    escaped = re.escape(axis)

    # H1/H2 headers only
    header_re = re.compile(
        r"^#{1,2}\s+.*" + escaped + r".*$",
        re.MULTILINE | re.IGNORECASE,
    )
    if header_re.search(content):
        return True

    # HTML CCD comment
    comment_re = re.compile(
        r"<!--\s*ccd:\s*" + escaped + r"\s*-->",
        re.IGNORECASE,
    )
    if comment_re.search(content):
        return True

    return False


# ---------------------------------------------------------------------------
# 4. Tier 3 -- Token frequency matching
# ---------------------------------------------------------------------------


def _axis_token_match(
    content: str,
    axis: str,
    min_tokens: int = 2,
    min_total: int = 3,
) -> bool:
    """Check if enough axis tokens appear frequently in *content*.

    Splits *axis* on ``-``, excludes :data:`TIER3_STOPWORDS`, then counts
    case-insensitive occurrences.  Returns True only when
    ``matched_tokens >= min_tokens`` AND ``total_count >= min_total``.
    """
    tokens = [t for t in axis.split("-") if t.lower() not in TIER3_STOPWORDS]

    # Axis too short for reliable matching
    if len(tokens) < 2:
        return False

    content_lower = content.lower()
    matched_tokens = 0
    total_count = 0

    for token in tokens:
        count = content_lower.count(token.lower())
        if count > 0:
            matched_tokens += 1
            total_count += count

    return matched_tokens >= min_tokens and total_count >= min_total


# ---------------------------------------------------------------------------
# 5. 3-tier cascade
# ---------------------------------------------------------------------------


def extract_axes(
    content: str,
    known_axes: list[str],
) -> list[dict[str, Any]]:
    """Run 3-tier axis extraction cascade.

    Returns list of ``{ccd_axis, association_type, extracted_confidence}``.
    If nothing matches, returns the ``unclassified`` sentinel.
    """
    results: list[dict[str, Any]] = []
    found_axes: set[str] = set()

    # Tier 1: Frontmatter (conf=1.0)
    fm_axes = _parse_frontmatter_axes(content)
    for axis in fm_axes:
        if axis in known_axes or axis not in known_axes:
            # Accept frontmatter axes even if not in known_axes vocabulary
            pass
        results.append(
            {
                "ccd_axis": axis,
                "association_type": "frontmatter",
                "extracted_confidence": 1.0,
            }
        )
        found_axes.add(axis)

    # Tier 2: Regex -- headers / comments (conf=0.7)
    for axis in known_axes:
        if axis in found_axes:
            continue
        if _axis_in_headers_or_comments(content, axis):
            results.append(
                {
                    "ccd_axis": axis,
                    "association_type": "regex",
                    "extracted_confidence": 0.7,
                }
            )
            found_axes.add(axis)

    # Tier 3: Keyword token matching (conf=0.4)
    for axis in known_axes:
        if axis in found_axes:
            continue
        if _axis_token_match(content, axis):
            results.append(
                {
                    "ccd_axis": axis,
                    "association_type": "keyword",
                    "extracted_confidence": 0.4,
                }
            )
            found_axes.add(axis)

    # Unclassified fallback
    if not results:
        return [
            {
                "ccd_axis": "unclassified",
                "association_type": "unclassified",
                "extracted_confidence": 0.0,
            }
        ]

    return results


# ---------------------------------------------------------------------------
# 6. Description extraction
# ---------------------------------------------------------------------------


def _extract_description(content: str, max_length: int = 200) -> str:
    """Extract first prose paragraph, skipping frontmatter and headings.

    Returns empty string if no prose found.
    """
    lines = content.split("\n")
    start = 0

    # Skip YAML frontmatter
    if lines and lines[0].rstrip() == "---":
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                start = i + 1
                break

    paragraph_lines: list[str] = []
    in_paragraph = False

    for line in lines[start:]:
        stripped = line.strip()

        # Skip blank, heading, and horizontal rule lines
        if not stripped:
            if in_paragraph:
                break  # end of paragraph
            continue
        if stripped.startswith("#"):
            if in_paragraph:
                break
            continue
        if stripped == "---":
            if in_paragraph:
                break
            continue

        paragraph_lines.append(stripped)
        in_paragraph = True

    if not paragraph_lines:
        return ""

    text = " ".join(paragraph_lines)
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# 7. Content hash
# ---------------------------------------------------------------------------


def _content_hash(content: str) -> str:
    """SHA-256 prefix hash consistent with project pattern."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 8. Bus safety check
# ---------------------------------------------------------------------------


def _bus_is_running(socket_path: str = DEFAULT_BUS_SOCKET) -> bool:
    """Check if the governance bus daemon is reachable via Unix socket."""
    sock = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
    try:
        sock.settimeout(1.0)
        sock.connect(socket_path)
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# 9. Full reindex
# ---------------------------------------------------------------------------


def reindex_docs(
    db_path: str = "data/ope.db",
    docs_dir: str = "docs",
    socket_path: str = DEFAULT_BUS_SOCKET,
    memory_md_path: str | None = None,
) -> dict[str, int]:
    """Walk *docs_dir*, extract axes, populate ``doc_index`` via DELETE+INSERT.

    Aborts with :class:`SystemExit` if the bus daemon is reachable (prevents
    concurrent DuckDB writes).
    """
    # Bus safety gate
    if _bus_is_running(socket_path):
        print(
            "[ERROR] Bus daemon is running. "
            "Stop it first: python -m src.pipeline.cli bus stop",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Load axis vocabulary
    known_axes = load_axis_vocabulary(db_path, memory_md_path)

    # Walk docs
    docs_path = Path(docs_dir)
    all_rows: list[tuple[str, str, str, float, str, None, str]] = []
    total_files = 0
    unclassified_files = 0
    unclassified_paths: list[str] = []

    for md_file in sorted(docs_path.rglob("*.md")):
        total_files += 1
        content = md_file.read_text(errors="replace")
        content_h = _content_hash(content)
        axes_info = extract_axes(content, known_axes)
        description = _extract_description(content)
        doc_path = str(md_file)

        is_unclassified = (
            len(axes_info) == 1
            and axes_info[0]["ccd_axis"] == "unclassified"
        )
        if is_unclassified:
            unclassified_files += 1
            unclassified_paths.append(doc_path)

        for axis_row in axes_info:
            all_rows.append(
                (
                    doc_path,
                    axis_row["ccd_axis"],
                    axis_row["association_type"],
                    axis_row["extracted_confidence"],
                    description,
                    None,  # section_anchor: NULL for Phase 21
                    content_h,
                )
            )

    # Write to DuckDB
    conn = duckdb.connect(db_path)
    try:
        from src.pipeline.live.bus.doc_schema import create_doc_schema

        create_doc_schema(conn)

        # Full refresh: DELETE + INSERT
        conn.execute("DELETE FROM doc_index")

        for row in all_rows:
            conn.execute(
                "INSERT INTO doc_index "
                "(doc_path, ccd_axis, association_type, extracted_confidence, "
                "description_cache, section_anchor, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                list(row),
            )
    finally:
        conn.close()

    # Axis distribution for stdout
    axis_counts: dict[str, int] = {}
    for row in all_rows:
        axis_counts[row[1]] = axis_counts.get(row[1], 0) + 1

    # Summary to stdout
    print(f"[OPE Doc Indexer] Indexed {total_files} files, {len(all_rows)} rows")
    print(f"[OPE Doc Indexer] Unclassified: {unclassified_files} files")
    print(f"[OPE Doc Indexer] Axes found: {len(axis_counts)} distinct")
    for axis, count in sorted(axis_counts.items()):
        print(f"  {axis}: {count}")

    # Unclassified to stderr for human review
    if unclassified_paths:
        print("\n[OPE Doc Indexer] Unclassified docs:", file=sys.stderr)
        for p in unclassified_paths:
            print(f"  {p}", file=sys.stderr)

    return {
        "total_files": total_files,
        "indexed_rows": len(all_rows),
        "unclassified_files": unclassified_files,
        "axes_found": len(axis_counts),
    }
