#!/usr/bin/env python3
"""
Standalone bidirectional archetype exclusivity auditor for ocg-standard-db.

Reads directly from `dump/*.jsonl` (no SQLite lock required) and evaluates
Master-format `cards.jsonl` against `archetypes.jsonl` and `card_archetypes.jsonl`
using the Smart First-Letter Case-Sensitive matching rule.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DUMP_DIR = ROOT / "dump"

ALLOWED_ARCH_OVERLAPS: set[tuple[str, str]] = {
    ("baaningunakkuru", "baaningunakkuraa"),
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def card_pool(card: dict[str, Any]) -> str:
    cid = card["id"]
    if cid < 4007 or cid >= 900000:
        return "VG"
    name = card["ocg_name"]
    if name.endswith(" Token") or name == "Token":
        return "TOKEN"
    return "OCG"


def ja_display(row: dict[str, Any]) -> str:
    return row.get("ja_base") or row.get("ja_kana") or ""


def ja_matches(arch: dict[str, Any], card: dict[str, Any]) -> bool:
    ja_a = ja_display(arch)
    if not ja_a:
        return False
    return (ja_a in (card.get("ja_base") or "")) or (ja_a in (card.get("ja_kana") or ""))


def has_rule_exclusion(arch_name: str, ocg_text: str | None) -> bool:
    """Return True if `ocg_text` explicitly excludes this card from `arch_name`."""
    if not ocg_text or not arch_name:
        return False
    cands = [arch_name]
    if arch_name[0].islower():
        cands.append(arch_name[0].upper() + arch_name[1:])
    alts = "|".join(re.escape(c) for c in cands)
    sep = r"(?:,\s*(?:or|and)\s+|,\s*|\s+(?:or|and)\s+)"
    pat = (
        rf'\(This card is not treated as an? '
        rf'(?:"[^"]+"{sep})*'
        rf'"(?:{alts})"'
        rf'(?:{sep}"[^"]+")*\s+card\.\)'
    )
    return bool(re.search(pat, ocg_text))


def match_archetype(arch_name: str, card_name: str, archetype_id: str | None = None) -> bool:
    """
    Canonical Smart First-Letter Case-Sensitive Rule:
    - `nanbaazu10x` / `kaosunanbaazu10x` ("Numbers 10X" / "Chaos Numbers 10X"): match 10[1-7]\\b.
    - `atorakushon`: normalize turned-A (`Ɐ`, U+2C6F) to `A`.
    - Lowercase-initial archetype names ("roid", "tellarknight", "verz", "code Talker"):
      match both lowercase and uppercase first letters.
    - All other Title-Case / ALL-CAPS names: strict exact case-sensitive substring.
    """
    if archetype_id == "atorakushon":
        card_name = card_name.replace("\u2c6f", "A")

    if archetype_id in ("nanbaazu10x", "kaosunanbaazu10x") and arch_name.endswith("10X"):
        prefix = re.escape(arch_name[:-3])
        return bool(re.search(rf"{prefix}10[1-7]\b", card_name))

    if arch_name and arch_name[0].islower():
        cap = arch_name[0].upper() + arch_name[1:]
        return (arch_name in card_name) or (cap in card_name)

    return arch_name in card_name


def run_audit(
    cards: list[dict[str, Any]],
    archetypes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    min_fp: int = 0,
    max_fp: int | None = None,
) -> dict[str, Any]:
    card_by_id = {c["id"]: c for c in cards}
    arch_by_id = {a["archetype_id"]: a for a in archetypes}

    arch_members: dict[str, set[int]] = {}
    arch_overrides: dict[str, set[int]] = {}
    for link in links:
        cid = link["card_id"]
        aid = link["archetype_id"]
        if cid not in card_by_id or aid not in arch_by_id:
            continue
        arch_members.setdefault(aid, set()).add(cid)
        if link.get("is_rule_override"):
            arch_overrides.setdefault(aid, set()).add(cid)

    # 1. False positives & 2. False negatives across all archetypes
    all_fps_by_arch: dict[str, list[dict[str, Any]]] = {}
    all_fns_by_arch: dict[str, list[dict[str, Any]]] = {}
    rule_excluded_pairs = 0
    for a in archetypes:
        aid = a["archetype_id"]
        aname = a["ocg_name"]
        mems = arch_members.get(aid, set())
        overrides = arch_overrides.get(aid, set())

        allowed_inner_mems: set[int] = set().union(
            *(arch_members.get(bid, set()) for oid, bid in ALLOWED_ARCH_OVERLAPS if oid == aid)
        )

        fps: list[dict[str, Any]] = []
        for c in cards:
            if c["id"] in mems or c["id"] in allowed_inner_mems:
                continue
            if match_archetype(aname, c["ocg_name"], aid):
                if has_rule_exclusion(aname, c.get("ocg_text")):
                    rule_excluded_pairs += 1
                    continue
                fps.append(
                    {
                        "id": c["id"],
                        "ocg_name": c["ocg_name"],
                        "tcg_name": c.get("tcg_name"),
                        "ja": ja_display(c),
                        "pool": card_pool(c),
                        "ja_match": ja_matches(a, c),
                    }
                )
        if fps:
            all_fps_by_arch[aid] = fps

        fns: list[dict[str, Any]] = []
        for cid in sorted(mems):
            if cid in overrides:
                continue
            c = card_by_id[cid]
            if not match_archetype(aname, c["ocg_name"], aid):
                fns.append(
                    {
                        "id": cid,
                        "ocg_name": c["ocg_name"],
                        "tcg_name": c.get("tcg_name"),
                        "ja": ja_display(c),
                        "pool": card_pool(c),
                        "ja_match": ja_matches(a, c),
                    }
                )
        if fns:
            all_fns_by_arch[aid] = fns

    # Filtered views for --min-fp / --max-fp
    fps_report: list[dict[str, Any]] = []
    for a in archetypes:
        aid = a["archetype_id"]
        fps = all_fps_by_arch.get(aid, [])
        n_fp = len(fps)
        if n_fp == 0:
            continue
        if n_fp < min_fp or (max_fp is not None and n_fp > max_fp):
            continue
        fps_report.append(
            {
                "archetype_id": aid,
                "ocg_name": a["ocg_name"],
                "tcg_name": a["tcg_name"],
                "ja": ja_display(a),
                "member_count": len(arch_members.get(aid, set())),
                "fp_count": n_fp,
                "ocg_fp_count": sum(1 for x in fps if x["pool"] == "OCG"),
                "vg_fp_count": sum(1 for x in fps if x["pool"] == "VG"),
                "token_fp_count": sum(1 for x in fps if x["pool"] == "TOKEN"),
                "ja_match_count": sum(1 for x in fps if x["ja_match"]),
                "collisions": fps,
            }
        )
    fps_report.sort(key=lambda x: (-x["fp_count"], x["archetype_id"]))

    fns_report: list[dict[str, Any]] = []
    for a in archetypes:
        aid = a["archetype_id"]
        fns = all_fns_by_arch.get(aid, [])
        if not fns:
            continue
        fns_report.append(
            {
                "archetype_id": aid,
                "ocg_name": a["ocg_name"],
                "tcg_name": a["tcg_name"],
                "ja": ja_display(a),
                "member_count": len(arch_members.get(aid, set())),
                "fn_count": len(fns),
                "misses": fns,
            }
        )
    fns_report.sort(key=lambda x: (-x["fn_count"], x["archetype_id"]))

    # 3. Archetype-in-archetype overlaps (non-sub-archetype A-in-B)
    arch_overlaps: list[dict[str, Any]] = []
    for a in archetypes:
        aid = a["archetype_id"]
        aname = a["ocg_name"]
        a_ja = ja_display(a)
        a_mems = arch_members.get(aid, set())
        for b in archetypes:
            bid = b["archetype_id"]
            if aid == bid or (aid, bid) in ALLOWED_ARCH_OVERLAPS:
                continue
            if not match_archetype(aname, b["ocg_name"], aid):
                continue
            b_ja = ja_display(b)
            b_mems = arch_members.get(bid, set())
            ja_sub = bool(a_ja and b_ja and (a_ja in b_ja))
            overlap = len(a_mems & b_mems)
            if not ja_sub and overlap < len(b_mems):
                arch_overlaps.append(
                    {
                        "outer_id": aid,
                        "outer_ocg": aname,
                        "outer_ja": a_ja,
                        "inner_id": bid,
                        "inner_ocg": b["ocg_name"],
                        "inner_ja": b_ja,
                        "member_overlap": overlap,
                        "inner_member_count": len(b_mems),
                    }
                )
    arch_overlaps.sort(key=lambda x: (x["outer_id"], x["inner_id"]))

    # 4. Mixed-case candidates (Title-Case archetypes with lowercase mid-word members)
    mixed_case: list[dict[str, Any]] = []
    for a in archetypes:
        aid = a["archetype_id"]
        aname = a["ocg_name"]
        if not aname or not aname[0].isupper():
            continue
        low_init = aname[0].lower() + aname[1:]
        mems = arch_members.get(aid, set())
        overrides = arch_overrides.get(aid, set())

        exact_mems = []
        lower_mems = []
        for cid in sorted(mems):
            if cid in overrides:
                continue
            c = card_by_id[cid]
            if aname in c["ocg_name"]:
                exact_mems.append(c)
            elif low_init in c["ocg_name"]:
                lower_mems.append(c)
        if not lower_mems:
            continue

        extra_fps = [
            {
                "id": c["id"],
                "ocg_name": c["ocg_name"],
                "ja": ja_display(c),
                "pool": card_pool(c),
                "ja_match": ja_matches(a, c),
            }
            for c in cards
            if c["id"] not in mems and aname not in c["ocg_name"] and low_init in c["ocg_name"]
        ]
        mixed_case.append(
            {
                "archetype_id": aid,
                "ocg_name": aname,
                "proposed_ocg_name": low_init,
                "tcg_name": a["tcg_name"],
                "ja": ja_display(a),
                "exact_member_count": len(exact_mems),
                "lower_member_count": len(lower_mems),
                "extra_fp_count": len(extra_fps),
                "exact_sample": [c["ocg_name"] for c in exact_mems[:2]],
                "lower_sample": [c["ocg_name"] for c in lower_mems[:3]],
                "extra_fps": extra_fps,
            }
        )
    mixed_case.sort(key=lambda x: (-x["lower_member_count"], x["extra_fp_count"], x["archetype_id"]))

    strict_violations = sum(
        1
        for a in archetypes
        if a["archetype_id"] in all_fps_by_arch or a["archetype_id"] in all_fns_by_arch
    )

    return {
        "counts": {
            "master_cards": len(cards),
            "archetypes_total": len(archetypes),
            "card_archetypes_master": sum(len(v) for v in arch_members.values()),
            "fp_archetypes": len(fps_report),
            "fp_pairs_total": sum(r["fp_count"] for r in fps_report),
            "fp_pairs_ocg": sum(r["ocg_fp_count"] for r in fps_report),
            "fp_pairs_vg": sum(r["vg_fp_count"] for r in fps_report),
            "fp_pairs_token": sum(r["token_fp_count"] for r in fps_report),
            "fp_pairs_ja_match": sum(r["ja_match_count"] for r in fps_report),
            "fn_archetypes": len(fns_report),
            "fn_pairs_total": sum(r["fn_count"] for r in fns_report),
            "arch_overlap_pairs": len(arch_overlaps),
            "mixed_case_candidates": len(mixed_case),
            "mixed_case_zero_extra_fp": sum(1 for m in mixed_case if m["extra_fp_count"] == 0),
            "rule_excluded_pairs": rule_excluded_pairs,
            "strict_violations": strict_violations,
        },
        "false_positives": fps_report,
        "false_negatives": fns_report,
        "arch_overlaps": arch_overlaps,
        "mixed_case": mixed_case,
    }


def _md_escape(text: str | None) -> str:
    return (text or "").replace("|", "\\|")


def format_summary(report: dict[str, Any], category: str) -> str:
    c = report["counts"]
    lines = [
        f"Audit Scope     : {c['archetypes_total']} archetypes, {c['master_cards']:,} Master cards, {c['card_archetypes_master']:,} links",
        f"False Positives : {c['fp_archetypes']} archetypes, {c['fp_pairs_total']:,} pairs (OCG={c['fp_pairs_ocg']:,}, VG={c['fp_pairs_vg']}, TOKEN={c['fp_pairs_token']}, JA_MATCH={c['fp_pairs_ja_match']})",
        f"False Negatives : {c['fn_archetypes']} archetypes, {c['fn_pairs_total']} unflagged (is_rule_override=0) pairs",
        f"Arch Overlaps   : {c['arch_overlap_pairs']} non-sub-archetype A-in-B pairs",
        f"Mixed-Case Cands: {c['mixed_case_candidates']} archetypes ({c['mixed_case_zero_extra_fp']} with 0 extra FPs)",
    ]
    if c.get("rule_excluded_pairs"):
        lines.append(f"Rule Exclusions : {c['rule_excluded_pairs']} pairs excluded via ocg_text")

    if category in ("fp", "all") and report["false_positives"]:
        lines.append("\n--- Top False Positives ---")
        for row in report["false_positives"][:30]:
            ex = ", ".join(
                f"{x['id']}:{x['ocg_name']}{'[JA]' if x['ja_match'] else ''}"
                for x in row["collisions"][:3]
            )
            lines.append(
                f"  {row['fp_count']:4d} (OCG={row['ocg_fp_count']:4d},VG={row['vg_fp_count']:2d},JA={row['ja_match_count']:2d}) "
                f"| {row['archetype_id']:24s} | {row['ocg_name']!r:20s} | {ex}"
            )
        if len(report["false_positives"]) > 30:
            lines.append(f"  ... +{len(report['false_positives']) - 30} more archetypes")

    if category in ("fn", "all") and report["false_negatives"]:
        lines.append("\n--- False Negatives (is_rule_override=0) ---")
        for row in report["false_negatives"]:
            ex = ", ".join(f"{x['id']}:{x['ocg_name']}" for x in row["misses"][:3])
            lines.append(
                f"  {row['fn_count']:3d} | {row['archetype_id']:24s} | {row['ocg_name']!r:20s} | {ex}"
            )

    if category in ("arch_overlap", "all") and report["arch_overlaps"]:
        lines.append("\n--- Archetype-in-Archetype Overlaps ---")
        for row in report["arch_overlaps"][:25]:
            lines.append(
                f"  {row['outer_id']} ({row['outer_ocg']!r}) IN "
                f"{row['inner_id']} ({row['inner_ocg']!r}) [overlap {row['member_overlap']}/{row['inner_member_count']}]"
            )
        if len(report["arch_overlaps"]) > 25:
            lines.append(f"  ... +{len(report['arch_overlaps']) - 25} more overlaps")

    if category in ("mixed_case", "all") and report["mixed_case"]:
        lines.append("\n--- Mixed-Case Candidates ---")
        for row in report["mixed_case"][:25]:
            lines.append(
                f"  lo={row['lower_member_count']:2d} ex={row['exact_member_count']:3d} extraFP={row['extra_fp_count']:2d} "
                f"| {row['archetype_id']:22s} | {row['ocg_name']!r} -> {row['proposed_ocg_name']!r}"
            )

    return "\n".join(lines)


def format_markdown(report: dict[str, Any], category: str) -> str:
    c = report["counts"]
    lines = [
        "# Archetype Exclusivity Audit Report",
        "",
        f"- **Master cards:** {c['master_cards']:,} | **Archetypes:** {c['archetypes_total']} | **Links:** {c['card_archetypes_master']:,}",
        f"- **False positives:** {c['fp_archetypes']} archetypes, {c['fp_pairs_total']:,} pairs (OCG={c['fp_pairs_ocg']:,}, VG={c['fp_pairs_vg']}, TOKEN={c['fp_pairs_token']}, `JA_MATCH`={c['fp_pairs_ja_match']})",
        f"- **False negatives (`is_rule_override=0`):** {c['fn_archetypes']} archetypes, {c['fn_pairs_total']} pairs",
        f"- **Archetype-in-archetype overlaps:** {c['arch_overlap_pairs']} | **Mixed-case candidates:** {c['mixed_case_candidates']} ({c['mixed_case_zero_extra_fp']} zero-extra-FP)",
        "",
    ]

    if category in ("fp", "all") and report["false_positives"]:
        lines.extend(
            [
                "## False Positives (Non-Member Collisions)",
                "",
                "| `archetype_id` | `ocg_name` | `tcg_name` | JA | Members | FPs (OCG/VG/TOK) | `JA_MATCH` | Sample Colliding Cards |",
                "| :--- | :--- | :--- | :--- | ---: | :--- | ---: | :--- |",
            ]
        )
        for row in report["false_positives"]:
            sample = "; ".join(
                f"`{x['id']}` {_md_escape(x['ocg_name'])} ({x['pool']}{', JA' if x['ja_match'] else ''})"
                for x in row["collisions"][:5]
            )
            if row["fp_count"] > 5:
                sample += f"; ... (+{row['fp_count'] - 5})"
            counts_str = f"{row['fp_count']} ({row['ocg_fp_count']}/{row['vg_fp_count']}/{row['token_fp_count']})"
            lines.append(
                f"| `{row['archetype_id']}` | `{_md_escape(row['ocg_name'])}` | "
                f"`{_md_escape(row['tcg_name'])}` | {_md_escape(row['ja'])} | {row['member_count']} | "
                f"{counts_str} | {row['ja_match_count']} | {sample} |"
            )
        lines.append("")

    if category in ("fn", "all") and report["false_negatives"]:
        lines.extend(
            [
                "## False Negatives (`is_rule_override = 0`)",
                "",
                "| `archetype_id` | `ocg_name` | JA | FNs | Sample Unmatched Members |",
                "| :--- | :--- | :--- | ---: | :--- |",
            ]
        )
        for row in report["false_negatives"]:
            sample = "; ".join(
                f"`{x['id']}` {_md_escape(x['ocg_name'])} ({_md_escape(x['ja'])})"
                for x in row["misses"][:5]
            )
            if row["fn_count"] > 5:
                sample += f"; ... (+{row['fn_count'] - 5})"
            lines.append(
                f"| `{row['archetype_id']}` | `{_md_escape(row['ocg_name'])}` | "
                f"{_md_escape(row['ja'])} | {row['fn_count']} | {sample} |"
            )
        lines.append("")

    if category in ("mixed_case", "all") and report["mixed_case"]:
        lines.extend(
            [
                "## Mixed-Case Candidates (Lowercase Mid-Word Members)",
                "",
                "| `archetype_id` | Current | Proposed | JA | Exact | Lower | Extra FPs | Lower Example | Extra FP Examples |",
                "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | :--- | :--- |",
            ]
        )
        for row in report["mixed_case"]:
            lo_ex = ", ".join(_md_escape(x) for x in row["lower_sample"][:2])
            fp_ex = ", ".join(f"`{x['id']}` {_md_escape(x['ocg_name'])}" for x in row["extra_fps"][:3])
            lines.append(
                f"| `{row['archetype_id']}` | `{_md_escape(row['ocg_name'])}` | "
                f"`{_md_escape(row['proposed_ocg_name'])}` | {_md_escape(row['ja'])} | {row['exact_member_count']} | "
                f"{row['lower_member_count']} | {row['extra_fp_count']} | {lo_ex} | {fp_ex} |"
            )
        lines.append("")

    if category in ("arch_overlap", "all") and report["arch_overlaps"]:
        lines.extend(
            [
                "## Archetype-in-Archetype Overlaps",
                "",
                "| Outer (`archetype_id`) | Outer `ocg_name` | Inner (`archetype_id`) | Inner `ocg_name` | Member Overlap |",
                "| :--- | :--- | :--- | :--- | ---: |",
            ]
        )
        for row in report["arch_overlaps"]:
            lines.append(
                f"| `{row['outer_id']}` | `{_md_escape(row['outer_ocg'])}` | "
                f"`{row['inner_id']}` | `{_md_escape(row['inner_ocg'])}` | {row['member_overlap']}/{row['inner_member_count']} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bidirectional Master-format archetype exclusivity auditor")
    parser.add_argument(
        "--category",
        choices=["fp", "fn", "arch_overlap", "mixed_case", "all"],
        default="all",
        help="Audit category to display (default: all)",
    )
    parser.add_argument("--min-fp", type=int, default=0, help="Minimum FP count filter")
    parser.add_argument("--max-fp", type=int, default=None, help="Maximum FP count filter")
    parser.add_argument("--format", choices=["summary", "md", "json"], default="summary", help="Output format")
    parser.add_argument("--out", type=Path, default=None, help="Optional file path to write output")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any FP or unflagged FN exists")
    args = parser.parse_args()

    cards = load_jsonl(DUMP_DIR / "cards.jsonl")
    archetypes = load_jsonl(DUMP_DIR / "archetypes.jsonl")
    links = load_jsonl(DUMP_DIR / "card_archetypes.jsonl")

    report = run_audit(
        cards,
        archetypes,
        links,
        min_fp=args.min_fp,
        max_fp=args.max_fp,
    )

    if args.format == "json":
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    elif args.format == "md":
        rendered = format_markdown(report, args.category)
    else:
        rendered = format_summary(report, args.category)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"Wrote audit report to {args.out}")
    else:
        print(rendered)

    if args.strict and report["counts"]["strict_violations"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
