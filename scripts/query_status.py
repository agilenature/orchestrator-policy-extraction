"""Print live OPE query index status — called by .claude/commands/query.md."""

import sys
import duckdb


def main() -> None:
    try:
        conn = duckdb.connect("data/ope.db", read_only=True)
    except Exception as e:
        print(f"[OPE] Could not open data/ope.db: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        episodes = conn.execute(
            "SELECT COUNT(*) FROM episode_search_text"
        ).fetchone()[0]

        axes = conn.execute("""
            SELECT ccd_axis, COUNT(*) as n
            FROM doc_index
            WHERE ccd_axis <> 'unclassified'
            GROUP BY ccd_axis
            ORDER BY n DESC
        """).fetchall()

        total_docs = sum(a[1] for a in axes)

        print(f"Episodes (BM25 searchable): {episodes}")
        print(f"Docs indexed: {total_docs} across {len(axes)} CCD axes")
        print()
        print("Indexed axes:")
        for axis, count in axes:
            bar = "█" * min(count, 20)
            print(f"  {bar} {axis} ({count})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
