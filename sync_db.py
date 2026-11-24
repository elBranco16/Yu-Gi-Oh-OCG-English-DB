#!/usr/bin/env python3
"""Deterministic SQLite <-> JSONL sync and Yugipedia override checks for ocg_standard.db."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "ocg_standard.db"
DUMP_DIR = ROOT / "dump"
SCHEMA_PATH = DUMP_DIR / "schema.sql"
INDEX_MARKER = "-- === INDEXES / TRIGGERS / VIEWS ==="

DEFAULT_CACHE_PATH = ROOT / ".cache" / "yugipedia_translations_cache.json"
USER_AGENT = "ocg-standard-db/1.0 (https://github.com/ocg-standard-db)"
YUGIPEDIA_API = "https://yugipedia.com/api.php"

CARD_COLUMNS = (
    "id",
    "ja_base",
    "ja_kana",
    "ocg_name",
    "tcg_name",
    "en_legacy_names",
    "ocg_text",
    "overriden_check",
)

BAD_TITLE_CHARS_RE = re.compile(r"[#\[\]{}|]")
REF_BLOCK_RE = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
REF_SELF_RE = re.compile(r"<ref[^>]*/?>", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"</?[^>]+>")
WIKI_PIPED_LINK_RE = re.compile(r"\[\[[^|\]]+\|([^\]]+)\]\]")
WIKI_SIMPLE_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
WS_RE = re.compile(r"\s+")


def get_pk_columns(con: sqlite3.Connection, table: str) -> list[str]:
    rows = con.execute(f'PRAGMA table_info("{table}")').fetchall()
    pks = sorted(((r[5], r[1]) for r in rows if r[5] > 0), key=lambda x: x[0])
    return [col for _, col in pks]


def export_db(db_path: Path) -> None:
    if not db_path.exists():
        sys.exit(f"Error: {db_path} not found.")

    DUMP_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            sys.exit(f"Aborting export: {len(fk_errors)} foreign key error(s) found: {fk_errors[:5]}")

        tables_ddl = [
            row[0].strip() + ";"
            for row in con.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        other_ddl = [
            row[0].strip() + ";"
            for row in con.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type IN ('index', 'trigger', 'view') AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
                "ORDER BY type, name"
            )
        ]

        schema_text = "\n\n".join(tables_ddl) + f"\n\n{INDEX_MARKER}\n\n" + "\n\n".join(other_ddl) + "\n"
        SCHEMA_PATH.write_text(schema_text, encoding="utf-8", newline="\n")

        table_names = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]

        expected_files = {f"{t}.jsonl" for t in table_names}
        for existing in DUMP_DIR.glob("*.jsonl"):
            if existing.name not in expected_files:
                existing.unlink()

        total_rows = 0
        for table in table_names:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
            pks = get_pk_columns(con, table)
            order_by = ", ".join(f'"{c}"' for c in pks) if pks else "rowid"

            out_path = DUMP_DIR / f"{table}.jsonl"
            count = 0
            with out_path.open("w", encoding="utf-8", newline="\n") as f:
                for row in con.execute(f'SELECT * FROM "{table}" ORDER BY {order_by}'):
                    obj = dict(zip(cols, row))
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    count += 1
            total_rows += count
            print(f"  exported {table:18s} ({count:,} rows)")

        print(f"Done: exported {len(table_names)} tables ({total_rows:,} total rows) to {DUMP_DIR.name}/")
    finally:
        con.close()


def _build_db(target_db: Path, verbose: bool = True, dump_dir: Path = DUMP_DIR) -> int:
    schema_path = dump_dir / "schema.sql"
    if not schema_path.exists():
        sys.exit(f"Error: {schema_path} not found.")

    schema_raw = schema_path.read_text(encoding="utf-8")
    if INDEX_MARKER in schema_raw:
        tables_sql, other_sql = schema_raw.split(INDEX_MARKER, 1)
    else:
        tables_sql, other_sql = schema_raw, ""

    if target_db.exists():
        target_db.unlink()

    con = sqlite3.connect(target_db)
    try:
        con.execute("PRAGMA foreign_keys = OFF")
        con.executescript(tables_sql)

        total_rows = 0
        for jsonl_path in sorted(dump_dir.glob("*.jsonl")):
            table = jsonl_path.stem
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(f'"{c}"' for c in cols)
            sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'

            batch = []
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError as exc:
                        sys.exit(f"JSON error in {jsonl_path.name}:{line_no}: {exc}")
                    batch.append([obj.get(c) for c in cols])

            con.executemany(sql, batch)
            total_rows += len(batch)
            if verbose:
                print(f"  imported {table:18s} ({len(batch):,} rows)")

        if other_sql.strip():
            con.executescript(other_sql)

        con.commit()
        con.execute("PRAGMA foreign_keys = ON")
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            sys.exit(f"Aborting: {len(fk_errors)} foreign key error(s) found: {fk_errors[:5]}")

        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            sys.exit(f"Aborting: integrity_check failed: {integrity}")
        return total_rows
    except BaseException:
        con.close()
        if target_db.exists():
            target_db.unlink()
        raise
    finally:
        con.close()


def import_db(db_path: Path) -> None:
    tmp_db = db_path.with_name(db_path.name + ".tmp")
    total_rows = _build_db(tmp_db, verbose=True)
    try:
        os.replace(tmp_db, db_path)
    except PermissionError:
        tmp_db.unlink(missing_ok=True)
        sys.exit(f"Error: {db_path.name} is open in another program. Close your SQLite editor and re-run.")
    print(f"Done: rebuilt {db_path.name} ({total_rows:,} total rows) with 0 FK/integrity errors.")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                sys.exit(f"JSON error in {path.name}:{line_no}: {exc}")
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            ordered = {col: row.get(col) for col in CARD_COLUMNS}
            f.write(json.dumps(ordered, ensure_ascii=False) + "\n")


def _http_get_json(url: str, retries: int = 4) -> Any:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if attempt == retries - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 1.5 * (attempt + 1)
            if exc.code == 429:
                delay = max(delay, 3.0 * (attempt + 1))
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}")


def _clean_yugi_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        raw = raw.get("fulltext") or raw.get("displaytitle") or ""
    txt = str(raw)
    if not txt:
        return ""
    txt = html.unescape(txt)
    txt = COMMENT_RE.sub("", txt)
    txt = REF_BLOCK_RE.sub("", txt)
    txt = REF_SELF_RE.sub("", txt)
    txt = BR_RE.sub(" ", txt)
    txt = HTML_TAG_RE.sub("", txt)
    txt = txt.replace("'''", "").replace("''", "")
    txt = WIKI_PIPED_LINK_RE.sub(r"\1", txt)
    txt = WIKI_SIMPLE_LINK_RE.sub(r"\1", txt)
    txt = txt.replace("\xa0", " ")
    return WS_RE.sub(" ", txt).strip()


def _clean_list(values: Any) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = _clean_yugi_text(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _smw_ask_raw(query: str) -> dict[str, Any]:
    url = f"{YUGIPEDIA_API}?action=ask&query={urllib.parse.quote(query)}&format=json"
    return _http_get_json(url)


def _smw_ask(query: str) -> dict[str, Any]:
    data = _smw_ask_raw(query)
    results = data.get("query", {}).get("results")
    if isinstance(results, dict):
        return results
    return {}


def _parse_smw_entry(page_title: str, payload: dict[str, Any]) -> dict[str, Any]:
    po = payload.get("printouts", {})
    english_list = _clean_list(po.get("English name"))
    english_name = english_list[0] if english_list else ""
    translated_names = _clean_list(po.get("Translated Japanese name"))
    base_translated_names = _clean_list(po.get("Translated Japanese base name"))
    medium = _clean_list(po.get("Medium"))
    return {
        "page": page_title,
        "english_name": english_name,
        "translated_names": translated_names,
        "base_translated_names": base_translated_names,
        "medium": medium,
    }


def _entry_rank(entry: dict[str, Any]) -> tuple[int, int, int]:
    """Lower tuple is better: prefer explicit translations/names and non-parenthesized titles."""
    has_name = 0 if (entry.get("translated_names") or entry.get("english_name")) else 1
    has_parens = 1 if "(" in entry.get("page", "") else 0
    return (has_name, has_parens, len(entry.get("page", "")))


def _pick_best_entry(existing: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return candidate
    return candidate if _entry_rank(candidate) < _entry_rank(existing) else existing


def load_cache(cache_path: Path, refresh: bool) -> dict[str, dict[str, Any]]:
    if not refresh and cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "by_db_id": dict(data.get("by_db_id") or {}),
                "by_internal_num": dict(data.get("by_internal_num") or {}),
                "by_title": dict(data.get("by_title") or {}),
            }
    return {"by_db_id": {}, "by_internal_num": {}, "by_title": {}}


def save_cache(cache_path: Path, cache: dict[str, dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _ingest_id_results(
    results: dict[str, Any],
    prop_name: str,
    target_bucket: dict[str, Any],
) -> None:
    for page_title, payload in results.items():
        if "#" in page_title:
            continue
        po = payload.get("printouts", {})
        raw_ids = po.get(prop_name) or []
        if not raw_ids:
            continue
        entry = _parse_smw_entry(page_title, payload)
        for raw_id in raw_ids:
            try:
                key = str(int(str(raw_id).strip()))
            except (TypeError, ValueError):
                continue
            target_bucket[key] = _pick_best_entry(target_bucket.get(key), entry)


def fetch_by_db_ids(
    db_ids: list[int],
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
    verbose: bool = True,
) -> None:
    bucket = cache["by_db_id"]
    needed = sorted({cid for cid in db_ids if str(cid) not in bucket})
    if not needed:
        return

    printouts = (
        "|?Database ID|?English name|?Translated Japanese name"
        "|?Translated Japanese base name|?Medium"
    )
    if verbose:
        print(f"Fetching {len(needed):,} Database IDs from Yugipedia SMW...")

    if len(needed) < 80:
        for i in range(0, len(needed), 10):
            chunk = needed[i : i + 10]
            q = f"[[Database ID::{'||'.join(map(str, chunk))}]]{printouts}|limit=500"
            res = _smw_ask(q)
            _ingest_id_results(res, "Database ID", bucket)
            for cid in chunk:
                bucket.setdefault(str(cid), None)
            time.sleep(0.15)
    else:
        min_id, max_id = min(needed), max(needed)
        needed_set = set(needed)
        for start in range((min_id // 400) * 400, max_id + 1, 400):
            end = start + 399
            if not any(start <= cid <= end for cid in needed_set):
                continue
            offset = 0
            while True:
                q = f"[[Database ID::≥{start}]][[Database ID::≤{end}]]{printouts}|limit=500|offset={offset}"
                data = _smw_ask_raw(q)
                res = data.get("query", {}).get("results")
                if isinstance(res, dict):
                    _ingest_id_results(res, "Database ID", bucket)
                cont = data.get("query-continue-offset")
                if cont is None:
                    break
                offset = int(cont)
                time.sleep(0.15)
            time.sleep(0.15)
        for cid in needed:
            bucket.setdefault(str(cid), None)

    save_cache(cache_path, cache)


def fetch_by_internal_nums(
    internal_ids: list[int],
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
    verbose: bool = True,
) -> None:
    bucket = cache["by_internal_num"]
    needed = sorted({cid for cid in internal_ids if str(cid) not in bucket})
    if not needed:
        return

    printouts = (
        "|?Internal number|?English name|?Translated Japanese name"
        "|?Translated Japanese base name|?Medium"
    )
    if verbose:
        print(f"Fetching {len(needed):,} Internal numbers from Yugipedia SMW...")

    for i in range(0, len(needed), 15):
        chunk = needed[i : i + 15]
        q = f"[[Internal number::{'||'.join(map(str, chunk))}]]{printouts}|limit=500"
        res = _smw_ask(q)
        _ingest_id_results(res, "Internal number", bucket)
        for cid in chunk:
            bucket.setdefault(str(cid), None)
        time.sleep(0.15)

    save_cache(cache_path, cache)


def card_title_candidates(card: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw: str | None) -> None:
        if not raw:
            return
        cand = raw.strip()
        if not cand or BAD_TITLE_CHARS_RE.search(cand) or cand in seen:
            return
        seen.add(cand)
        candidates.append(cand)

    _add(card.get("tcg_name"))
    _add(card.get("ocg_name"))
    legacy = card.get("en_legacy_names") or ""
    for part in legacy.split(";"):
        _add(part)
    return candidates


def _extract_template_param(wikitext: str, param: str) -> str:
    m = re.search(
        rf"^\|\s*{re.escape(param)}\s*=\s*(.+?)(?=\n\|\s*[a-zA-Z0-9_]+\s*=|\n\}})",
        wikitext,
        flags=re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _resolve_mw_titles(titles: list[str]) -> dict[str, str]:
    """Resolve candidate titles to existing canonical Yugipedia page titles (following redirects)."""
    resolved: dict[str, str] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i : i + 40]
        url = (
            f"{YUGIPEDIA_API}?action=query&titles={urllib.parse.quote('|'.join(chunk))}"
            "&redirects=1&format=json&formatversion=2"
        )
        query = _http_get_json(url).get("query", {})
        norm_map = {n["from"]: n["to"] for n in query.get("normalized", [])}
        red_map = {r["from"]: r["to"] for r in query.get("redirects", [])}
        existing_pages = {
            p["title"]
            for p in query.get("pages", [])
            if not p.get("missing") and not p.get("invalid")
        }
        for cand in chunk:
            cur = norm_map.get(cand, cand)
            visited: set[str] = set()
            while cur in red_map and cur not in visited:
                visited.add(cur)
                cur = red_map[cur]
            if cur in existing_pages:
                resolved[cand] = cur
        time.sleep(0.15)
    return resolved


def _fetch_wikitext_entries(canonical_titles: list[str]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for i in range(0, len(canonical_titles), 40):
        chunk = canonical_titles[i : i + 40]
        url = (
            f"{YUGIPEDIA_API}?action=query&titles={urllib.parse.quote('|'.join(chunk))}"
            "&prop=revisions&rvprop=content&rvslots=main&format=json&formatversion=2"
        )
        pages = _http_get_json(url).get("query", {}).get("pages", [])
        for p in pages:
            if p.get("missing") or p.get("invalid"):
                continue
            title = p["title"]
            revs = p.get("revisions") or []
            if not revs:
                continue
            wt = revs[0].get("slots", {}).get("main", {}).get("content", "")
            trans_raw = _extract_template_param(wt, "translated_name") or _extract_template_param(wt, "trans_name")
            name_raw = _extract_template_param(wt, "name") or title
            trans_clean = _clean_yugi_text(trans_raw)
            name_clean = _clean_yugi_text(name_raw)
            entries[title] = {
                "page": title,
                "english_name": name_clean,
                "translated_names": [trans_clean] if trans_clean else [],
                "base_translated_names": [],
                "medium": [],
            }
        time.sleep(0.15)
    return entries


def fetch_by_titles(
    cards: list[dict[str, Any]],
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
    verbose: bool = True,
) -> None:
    by_title = cache["by_title"]
    uncached_titles: list[str] = []
    seen: set[str] = set()
    for card in cards:
        for cand in card_title_candidates(card):
            if cand not in by_title and cand not in seen:
                seen.add(cand)
                uncached_titles.append(cand)

    if not uncached_titles:
        return

    if verbose:
        print(f"Resolving {len(uncached_titles):,} candidate title(s) on Yugipedia...")

    cand_to_canonical = _resolve_mw_titles(uncached_titles)
    canonical_needed = sorted({canon for canon in cand_to_canonical.values() if canon not in by_title})

    if canonical_needed:
        printouts = (
            "|?Database ID|?Internal number|?English name|?Translated Japanese name"
            "|?Translated Japanese base name|?Medium"
        )
        for i in range(0, len(canonical_needed), 12):
            chunk = canonical_needed[i : i + 12]
            q = f"[[{'||'.join(chunk)}]]{printouts}|limit=500"
            res = _smw_ask(q)
            for page_title, payload in res.items():
                if "#" in page_title:
                    continue
                entry = _parse_smw_entry(page_title, payload)
                by_title[page_title] = entry
            time.sleep(0.15)

        missing_smw = [canon for canon in canonical_needed if canon not in by_title]
        if missing_smw:
            wt_entries = _fetch_wikitext_entries(missing_smw)
            for canon in missing_smw:
                by_title[canon] = wt_entries.get(canon)

    for cand in uncached_titles:
        canon = cand_to_canonical.get(cand)
        if canon is not None:
            by_title[cand] = by_title.get(canon)
        else:
            by_title[cand] = None

    save_cache(cache_path, cache)


def resolve_card_entry(card: dict[str, Any], cache: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    cid = card["id"]
    if 4007 <= cid < 900000:
        entry = cache["by_db_id"].get(str(cid))
        if entry is not None:
            return entry
    elif cid < 4007:
        entry = cache["by_internal_num"].get(str(cid))
        if entry is not None:
            return entry

    for cand in card_title_candidates(card):
        entry = cache["by_title"].get(cand)
        if entry is not None:
            return entry
    return None


def extract_yugipedia_translations(
    entry: dict[str, Any],
    only_explicit_translated: bool,
) -> tuple[list[str], str | None]:
    translated = entry.get("translated_names") or []
    if translated:
        return list(translated), "translated_name"
    if only_explicit_translated:
        return [], None
    english_name = entry.get("english_name") or ""
    if english_name:
        return [english_name], "english_name"
    page_title = re.sub(r"\s*\(card\)$", "", entry.get("page", "")).strip()
    if page_title:
        return [page_title], "page_title"
    return [], None


def names_match(ocg_name: str, candidates: list[str], ignore_case: bool) -> bool:
    if ignore_case:
        target = ocg_name.casefold()
        return any(target == c.casefold() for c in candidates)
    return ocg_name in candidates


def write_report(report_path: Path, report_data: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.suffix.lower() == ".csv":
        fieldnames = [
            "table",
            "id",
            "ocg_name",
            "tcg_name",
            "yugipedia_page",
            "translation_source",
            "yugipedia_translations",
            "status",
            "old_overriden_check",
            "new_overriden_check",
        ]
        with report_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in report_data["items"]:
                row = dict(item)
                row["yugipedia_translations"] = " | ".join(item.get("yugipedia_translations") or [])
                writer.writerow(row)
    else:
        report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_overriden_names(
    dump_dir: Path = DUMP_DIR,
    tables: list[str] | None = None,
    ids: list[int] | None = None,
    dry_run: bool = False,
    refresh_cache: bool = False,
    cache_path: Path = DEFAULT_CACHE_PATH,
    only_explicit_translated: bool = False,
    ignore_case: bool = False,
    reset_matching: bool = False,
    report: Path | None = None,
    limit_preview: int = 25,
) -> bool:
    """Compare `ocg_name` against Yugipedia translations and mark mismatches with `overriden_check=1`."""
    selected_tables = tables or ["cards", "rush_cards"]
    id_filter = set(ids) if ids else None

    tables_data: dict[str, list[dict[str, Any]]] = {}
    target_cards: list[dict[str, Any]] = []
    for table in selected_tables:
        jsonl_path = dump_dir / f"{table}.jsonl"
        if not jsonl_path.exists():
            sys.exit(f"Error: {jsonl_path} not found.")
        rows = load_jsonl(jsonl_path)
        tables_data[table] = rows
        for row in rows:
            if id_filter is None or row["id"] in id_filter:
                target_cards.append(row)

    cache = load_cache(cache_path, refresh=refresh_cache)

    std_ids = [c["id"] for c in target_cards if 4007 <= c["id"] < 900000]
    vg_internal_ids = [c["id"] for c in target_cards if c["id"] < 4007]

    fetch_by_db_ids(std_ids, cache, cache_path)
    fetch_by_internal_nums(vg_internal_ids, cache, cache_path)

    unresolved_cards = [c for c in target_cards if resolve_card_entry(c, cache) is None]
    if unresolved_cards:
        fetch_by_titles(unresolved_cards, cache, cache_path)

    summary_by_table: dict[str, dict[str, int]] = {}
    report_items: list[dict[str, Any]] = []
    any_modified = False

    for table, rows in tables_data.items():
        stats = {
            "checked": 0,
            "flipped_to_1": 0,
            "already_1_mismatch": 0,
            "matched_preserved_1": 0,
            "matched_reset_to_0": 0,
            "matched_0": 0,
            "no_explicit_translation": 0,
            "not_found": 0,
        }
        table_modified = False
        preview_flips: list[dict[str, Any]] = []

        for row in rows:
            if id_filter is not None and row["id"] not in id_filter:
                continue
            stats["checked"] += 1
            old_val = int(row.get("overriden_check") or 0)
            new_val = old_val

            entry = resolve_card_entry(row, cache)
            if entry is None:
                stats["not_found"] += 1
                report_items.append(
                    {
                        "table": table,
                        "id": row["id"],
                        "ocg_name": row["ocg_name"],
                        "tcg_name": row.get("tcg_name"),
                        "yugipedia_page": None,
                        "translation_source": None,
                        "yugipedia_translations": [],
                        "status": "not_found",
                        "old_overriden_check": old_val,
                        "new_overriden_check": new_val,
                    }
                )
                continue

            candidates, source = extract_yugipedia_translations(entry, only_explicit_translated)
            if not candidates:
                stats["no_explicit_translation"] += 1
                status = "no_explicit_translation"
            elif names_match(row["ocg_name"], candidates, ignore_case):
                if old_val == 1:
                    if reset_matching:
                        new_val = 0
                        stats["matched_reset_to_0"] += 1
                        status = "matched_reset_to_0"
                    else:
                        stats["matched_preserved_1"] += 1
                        status = "matched_preserved_1"
                else:
                    stats["matched_0"] += 1
                    status = "matched_0"
            else:
                new_val = 1
                if old_val == 0:
                    stats["flipped_to_1"] += 1
                    status = "flipped_to_1"
                else:
                    stats["already_1_mismatch"] += 1
                    status = "already_1_mismatch"

            if new_val != old_val:
                row["overriden_check"] = new_val
                table_modified = True
                any_modified = True
                if len(preview_flips) < limit_preview:
                    preview_flips.append(
                        {
                            "id": row["id"],
                            "ocg_name": row["ocg_name"],
                            "tcg_name": row.get("tcg_name"),
                            "yugipedia": candidates,
                            "source": source,
                            "old": old_val,
                            "new": new_val,
                        }
                    )

            report_items.append(
                {
                    "table": table,
                    "id": row["id"],
                    "ocg_name": row["ocg_name"],
                    "tcg_name": row.get("tcg_name"),
                    "yugipedia_page": entry.get("page"),
                    "translation_source": source,
                    "yugipedia_translations": candidates,
                    "status": status,
                    "old_overriden_check": old_val,
                    "new_overriden_check": new_val,
                }
            )

        summary_by_table[table] = stats
        print(
            f"[{table}] checked={stats['checked']:,} "
            f"flipped_to_1={stats['flipped_to_1']:,} "
            f"already_1_mismatch={stats['already_1_mismatch']:,} "
            f"matched_0={stats['matched_0']:,} "
            f"matched_preserved_1={stats['matched_preserved_1']:,} "
            f"matched_reset_to_0={stats['matched_reset_to_0']:,} "
            f"no_explicit_translation={stats['no_explicit_translation']:,} "
            f"not_found={stats['not_found']:,}"
        )

        if preview_flips:
            action_label = "Would update" if dry_run else "Updated"
            print(f"  {action_label} (showing {len(preview_flips)}):")
            for item in preview_flips:
                print(
                    f"    {item['id']:>6} | {item['old']} -> {item['new']} | "
                    f"ocg={item['ocg_name']!r} vs yugi={item['yugipedia']!r} ({item['source']})"
                )

        if table_modified and not dry_run:
            out_path = dump_dir / f"{table}.jsonl"
            write_jsonl(out_path, rows)
            print(f"  Wrote {out_path}")

    if report:
        report_payload = {"summary": summary_by_table, "items": report_items}
        write_report(report, report_payload)
        print(f"Wrote report to {report}")

    return any_modified


def check_dump(
    dump_dir: Path = DUMP_DIR,
    db_path: Path = DEFAULT_DB,
    skip_yugipedia: bool = False,
    sync_db_after: bool = False,
    dry_run: bool = False,
    tables: list[str] | None = None,
    ids: list[int] | None = None,
    refresh_cache: bool = False,
    cache_path: Path = DEFAULT_CACHE_PATH,
    only_explicit_translated: bool = False,
    ignore_case: bool = False,
    reset_matching: bool = False,
    report: Path | None = None,
    limit_preview: int = 25,
) -> None:
    any_modified = False
    if not skip_yugipedia:
        any_modified = check_overriden_names(
            dump_dir=dump_dir,
            tables=tables,
            ids=ids,
            dry_run=dry_run,
            refresh_cache=refresh_cache,
            cache_path=cache_path,
            only_explicit_translated=only_explicit_translated,
            ignore_case=ignore_case,
            reset_matching=reset_matching,
            report=report,
            limit_preview=limit_preview,
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "check.db"
        total_rows = _build_db(tmp_db, verbose=True, dump_dir=dump_dir)
    print(f"OK: {dump_dir.name}/ validated cleanly ({total_rows:,} total rows, 0 JSON/FK/integrity errors).")

    if any_modified and not dry_run:
        if sync_db_after and dump_dir.resolve() == DUMP_DIR.resolve():
            print(f"Syncing {db_path.name} from {dump_dir.name}/...")
            import_db(db_path)
        else:
            print("Note: dump/*.jsonl was updated; run 'python sync_db.py import' to rebuild ocg_standard.db.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ocg_standard.db <-> dump/*.jsonl")
    parser.add_argument("command", choices=["export", "import", "check"])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database (default: ./ocg_standard.db)")
    parser.add_argument("--dump-dir", type=Path, default=DUMP_DIR, help="Path to dump directory (default: ./dump)")
    parser.add_argument("--dry-run", action="store_true", help="[check] Preview overriden_check changes without modifying dump/*.jsonl.")
    parser.add_argument("--skip-yugipedia", action="store_true", help="[check] Skip Yugipedia overriden_check pass and run offline validation only.")
    parser.add_argument("--sync-db", action="store_true", help="[check] Rebuild --db via import_db() if dump/*.jsonl was updated.")
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=["cards", "rush_cards"],
        default=["cards", "rush_cards"],
        help="[check] Card tables to check against Yugipedia (default: cards rush_cards).",
    )
    parser.add_argument("--ids", nargs="+", type=int, help="[check] Only check specific card IDs against Yugipedia.")
    parser.add_argument("--refresh-cache", action="store_true", help="[check] Ignore cached Yugipedia lookups and re-fetch.")
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="[check] Path to Yugipedia cache JSON (default: .cache/yugipedia_translations_cache.json).",
    )
    parser.add_argument(
        "--only-explicit-translated",
        action="store_true",
        help="[check] Only compare against Yugipedia's explicit `Translated Japanese name`.",
    )
    parser.add_argument("--ignore-case", action="store_true", help="[check] Use case-insensitive comparison.")
    parser.add_argument(
        "--reset-matching",
        action="store_true",
        help="[check] Reset overriden_check from 1 to 0 when ocg_name matches Yugipedia's translation.",
    )
    parser.add_argument("--report", type=Path, help="[check] Optional output path (.json or .csv) for full check details.")
    parser.add_argument("--limit-preview", type=int, default=25, help="[check] Max sample changes to print (default: 25).")
    args = parser.parse_args()

    if args.command == "export":
        export_db(args.db)
    elif args.command == "import":
        import_db(args.db)
    elif args.command == "check":
        check_dump(
            dump_dir=args.dump_dir,
            db_path=args.db,
            skip_yugipedia=args.skip_yugipedia,
            sync_db_after=args.sync_db,
            dry_run=args.dry_run,
            tables=args.tables,
            ids=args.ids,
            refresh_cache=args.refresh_cache,
            cache_path=args.cache_path,
            only_explicit_translated=args.only_explicit_translated,
            ignore_case=args.ignore_case,
            reset_matching=args.reset_matching,
            report=args.report,
            limit_preview=args.limit_preview,
        )


if __name__ == "__main__":
    main()
