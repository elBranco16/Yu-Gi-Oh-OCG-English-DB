#!/usr/bin/env python3
"""Deterministic SQLite <-> JSONL sync for Git collaboration on ocg_standard.db."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "ocg_standard.db"
DUMP_DIR = ROOT / "dump"
SCHEMA_PATH = DUMP_DIR / "schema.sql"
INDEX_MARKER = "-- === INDEXES / TRIGGERS / VIEWS ==="


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


def _build_db(target_db: Path, verbose: bool = True) -> int:
    if not SCHEMA_PATH.exists():
        sys.exit(f"Error: {SCHEMA_PATH} not found.")

    schema_raw = SCHEMA_PATH.read_text(encoding="utf-8")
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
        for jsonl_path in sorted(DUMP_DIR.glob("*.jsonl")):
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


def check_dump() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "check.db"
        total_rows = _build_db(tmp_db, verbose=True)
    print(f"OK: dump/ validated cleanly ({total_rows:,} total rows, 0 JSON/FK/integrity errors).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ocg_standard.db <-> dump/*.jsonl")
    parser.add_argument("command", choices=["export", "import", "check"])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database (default: ./ocg_standard.db)")
    args = parser.parse_args()

    if args.command == "export":
        export_db(args.db)
    elif args.command == "import":
        import_db(args.db)
    elif args.command == "check":
        check_dump()


if __name__ == "__main__":
    main()
