# Yu-Gi-Oh! OCG Standard Database

A collaborative, Git-friendly Master OCG Standard database covering **34,414 rows across 10 tables** of Yu-Gi-Oh! cards (OCG, Rush Duel, and game-only), archetypes, thematic series, characters, and core terminology.

All tables are stored as deterministic, primary-key-sorted **JSON Lines (`dump/*.jsonl`)** alongside `dump/schema.sql`, and can be rebuilt into `ocg_standard.db` on demand with `sync_db.py` or edited visually via **OCG Standard DB Studio**.

---

## Repository Structure

```text
.
├── Start-Studio.bat                  # Windows launcher for OCG Standard DB Studio
├── app/                              # Local web curation workbench (Python 3.10+ stdlib + vanilla JS/CSS)
├── sync_db.py                        # Export/import/check/diff-ids between SQLite and dump/, plus Yugipedia overriden_check sync
├── apply_text_mod.py                 # Populate/update ocg_text & en_legacy_names (erratas, numbering, PSCT shortening, OCG localization)
├── audit_archetypes.py               # Bidirectional Master-format archetype exclusivity & false-negative auditor
├── AGENTS.md                         # Repository governance, invariants, conflict priority & verification gate
├── DECISIONS.md                      # Settled translation precedents & policy rulings (DEC-001+)
├── STATUS.md                         # Git-tracked project status, table counts & batch log
├── .agents/
│   ├── skills/
│   │   ├── translate-card-name/      # Card, archetype, series, character & term naming/romanization rules
│   │   └── ocg-text-terms/           # ocg_text, terms.jsonl, -Race suffixing, flavor text & propagation rules
│   └── workflows/
│       └── batch.md                  # End-to-end /batch curation runbook (Phases 1–5)
├── .opencode/
│   └── command/
│       └── batch.md                  # OpenCode /batch slash-command shim
├── tests/
│   ├── test_audit_archetypes.py      # Archetype matcher & rule-exclusion regression tests
│   ├── test_studio_backend.py        # OCG Standard DB Studio backend & HTTP integration tests
│   └── test_sync_db.py               # sync_db import guard, invariants, diff-ids & Cemetery(ies) tests
└── dump/
    ├── schema.sql                    # Exact SQLite table & index definitions
    ├── cards.jsonl                   # 14,975 Master-format cards (OCG, game-only, Tokens)
    ├── rush_cards.jsonl              # 2,839 Rush Duel cards
    ├── gba_cards.jsonl               # 28 GBA-exclusive DM7/DM8 non-OCG cards
    ├── archetypes.jsonl              # 615 official OCG archetypes
    ├── series.jsonl                  # 369 thematic series
    ├── card_archetypes.jsonl         # 10,098 Master card <-> archetype links
    ├── card_series.jsonl             # 2,049 Master card <-> series links
    ├── rush_card_series.jsonl        # 1,943 Rush card <-> series links
    ├── characters.jsonl              # 1,474 characters
    └── terms.jsonl                   # 24 core OCG terminology entries
```

---

## Schema & Data Conventions

| Table | Columns |
| :--- | :--- |
| `cards` | `id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name`, `en_legacy_names`, `ocg_text`, `overriden_check` |
| `rush_cards` | `id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name`, `en_legacy_names`, `ocg_text`, `overriden_check` |
| `gba_cards` | `id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name`, `en_legacy_names`, `ocg_text`, `overriden_check` |
| `archetypes` | `archetype_id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name` |
| `series` | `series_id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name` |
| `card_archetypes` | `card_id`, `archetype_id`, `is_rule_override` |
| `card_series` | `card_id`, `series_id` |
| `rush_card_series` | `card_id`, `series_id` |
| `characters` | `character_id`, `series`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_dub_name` |
| `terms` | `term_id`, `category`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_en`, `en_legacy_terms` |

### Key Conventions
- **Card IDs (`cards.id` / `rush_cards.id` / `gba_cards.id`):** Uses the official Konami Card Database ID (`cid`, e.g., `4007` for *Blue-Eyes White Dragon*, `15150` for *Sevens Road Magician*) as well as `< 4007` retro/video-game IDs. Cards without a Konami `cid` or whose `< 4007` slot is occupied (such as Tokens or older game variants) use sequential IDs starting at `900001`. Standalone `gba_cards.id` uses the official in-game DM7 card number with DM8 fallback (`110`–`898`).
- **Entity IDs (`archetype_id`, `series_id`, `character_id`, `term_id`):** `archetype_id` and `series_id` use lowercase ASCII romaji `snake_case` slugs from `ja_kana` (preserving `ou`/`uu`, doubling katakana `ー`, and keeping `_rush` on Rush Duel series). `character_id` and `term_id` use lowercase ASCII `snake_case` slugs (with `_type`/`_attr`/`_subtype` collision suffixes on `terms`).
- **Japanese Names (`ja_base` / `ja_kana`):** `ja_kana` stores the reading/kana; `ja_base` is `null` whenever identical to `ja_kana`. `gba_cards` preserves verbatim GBA in-game Japanese spelling in `ja_base` (`null` when identical to `ja_kana`).
- **TCG Divergence (`tcg_name` / `tcg_dub_name`):** Populated only when the TCG card, archetype, series, or dub character name differs from `ocg_name`; otherwise `null`. Alternate official/game name variants (e.g., `#1` punctuation differences) are merged into clean `; `-separated `en_legacy_names`.
- **Card Text Formatting (`ocg_text`):** Combines official/community effect erratas, `① ② ③` effect numbering (Master `cards.jsonl`), standard PSCT shortenings, and full OCG card/archetype/terminology localization (`terms.jsonl`). Rush Duel cards preserve `[Requirement]` / `[Effect]` blocks; `gba_cards` preserve DM7/DM8 concise text.
- **Yugipedia Divergence Flag (`overriden_check`):** `1` marks an `ocg_name` that differs from Yugipedia's baseline translation (`0` is default; `DEC-012`). Maintained automatically by `sync_db.py check` and Studio Save & Export, and also set manually during offline `--skip-yugipedia` curations when clearly diverging.

---

## Governance & AI-Assisted Curation

Naming standards, terminology rules, and batch workflows are governed by a four-layer documentation structure:
1. **`AGENTS.md`** — Global invariants, 5-level naming conflict priority (Archetype Integrity → Furigana → Word Order → Articles → Punctuation/Capitalization), stop-and-ask boundaries, and the mandatory verification gate.
2. **`.agents/skills/`** — Detailed domain rules for naming/romanization (`translate-card-name/SKILL.md`) and `ocg_text` localization/propagation (`ocg-text-terms/SKILL.md`).
3. **`.agents/workflows/batch.md`** (and `.opencode/command/batch.md` for OpenCode `/batch`) — Step-by-step batch execution protocol from clean-worktree pre-flight and guarded SQLite sync through `diff-ids` auditing and bookkeeping.
4. **`DECISIONS.md` & `STATUS.md`** — Settled policy precedents (`DEC-001`–`DEC-013`) and Git-tracked session status.

---

## Requirements

- **Python 3.10+** (standard library only — no `pip install` needed).

---

## Editing Workflow

### Option A: Visual Curation Studio (Recommended)
Double-click `Start-Studio.bat` (or run `python app/server.py`) to launch **OCG Standard DB Studio** in your browser:
- Automatically checks `ocg_standard.db` against `dump/*.jsonl` on startup (auto-importing if missing, or letting you resume vs. rebuild fresh with a `.cache/backups/` snapshot if local edits exist).
- Filter & edit all 10 tables (`cards`, `rush_cards`, `gba_cards`, `archetypes`, `series`, `characters`, `terms`, and link tables) with Archetype/Series multi-filters, regex & Japanese search, live archetype collision warnings, inline Yugipedia & Konami OCG DB links, OCG terminology linting, Safe Rename reference propagation, and bulk find & replace.
- **Save & Export** (`Ctrl+S`) runs SQLite integrity checks, `audit_archetypes`, and cached Yugipedia `overriden_check` validation before exporting deterministic `dump/*.jsonl` files.
- **Commit & Push** previews `git diff dump/`, auto-generates a commit message, and runs `git add dump/` → `commit` → `pull --rebase` → `push`.

### Option B: Edit `dump/*.jsonl` Directly (Quick Text Edits)
```bash
git pull
# Edit dump/*.jsonl in VS Code or any UTF-8 text editor
python sync_db.py check --skip-yugipedia   # Validate JSON, FKs, SQLite integrity & data invariants (omit flag to refresh overriden_check)
python sync_db.py import --force           # Keep local ocg_standard.db synced with dump/
python audit_archetypes.py --strict        # Required: 0 Master archetype violations
python sync_db.py diff-ids                 # Review exact changed primary keys
git add dump/
git commit -m "Describe your edits"
git pull --rebase
git push
```

### Option C: Edit Visually in DB Browser for SQLite
```bash
git pull
python sync_db.py import                   # Builds local ocg_standard.db (aborts if DB has unexported edits; pass --force to overwrite)
# Open and edit ocg_standard.db in DB Browser for SQLite, then SAVE and CLOSE it
python sync_db.py export                   # Exports your changes back to dump/*.jsonl
python sync_db.py check --skip-yugipedia   # Verify JSON, FKs, integrity & invariants
python audit_archetypes.py --strict        # Verify 0 Master archetype violations
python sync_db.py diff-ids                 # Optional: inspect exact changed primary keys
git add dump/
git commit -m "Describe your edits"
git pull --rebase
git push
```

> **Note:** Always close your SQLite editor before running `sync_db.py export` or `sync_db.py import` so uncommitted changes in `-wal` files are flushed and the `.db` file is not locked.

---

## `sync_db.py` Commands

| Command | Description |
| :--- | :--- |
| `python sync_db.py check` | Compares `cards.jsonl`, `rush_cards.jsonl`, and `gba_cards.jsonl` against Yugipedia's Japanese name translations (**writes** `overriden_check = 1` mismatches to `dump/*.jsonl` unless `--dry-run` or `--skip-yugipedia` is passed, cached in `.cache/yugipedia_translations_cache.json`), validates all `dump/*.jsonl` files in a temporary SQLite DB (JSON syntax, primary keys, foreign keys, integrity), and enforces all semantic data invariants (`tcg_name != ocg_name`, `ja_base != ja_kana`, `0`/`1` flags, trimmed non-empty strings, clean `; ` legacy lists). |
| `python sync_db.py import` | Rebuilds `./ocg_standard.db` from `dump/`. Guards against overwriting a diverged local DB unless `--force` is passed. Supports `--db <path>`, `--dump-dir <path>`, and `--force`. |
| `python sync_db.py export` | Exports `./ocg_standard.db` back into sorted, UTF-8/LF `dump/*.jsonl` files and `dump/schema.sql`. Supports `--db <path>`. |
| `python sync_db.py diff-ids` | Compares working-tree `dump/*.jsonl` primary keys against a Git ref (default `HEAD`) and reports exact added, modified (with changed column names), and deleted IDs per table. Supports `--base <ref>`, `--dump-dir <path>`, and `--json`. |

### `sync_db.py check` Options

```bash
python sync_db.py check --dry-run            # Preview overriden_check changes without modifying dump/*.jsonl
python sync_db.py check --sync-db            # Also rebuild ocg_standard.db if dump/*.jsonl was updated
python sync_db.py check --skip-yugipedia     # Run offline JSONL/SQLite/invariant validation only
```

| Flag | Description |
| :--- | :--- |
| `--dry-run` | Preview `overriden_check` changes without modifying `dump/*.jsonl`. |
| `--sync-db` | Rebuild `--db` via `import --force` automatically if `dump/*.jsonl` was updated. |
| `--skip-yugipedia` | Skip the Yugipedia lookup pass and run offline JSONL/SQLite/invariant validation only. |
| `--tables` | Card tables to check (`cards`, `rush_cards`, `gba_cards`; default: all three). |
| `--ids` | Only check specific card IDs against Yugipedia. |
| `--dump-dir` | Path to dump directory (default: `./dump`). |
| `--refresh-cache` | Ignore `.cache/yugipedia_translations_cache.json` and re-fetch from Yugipedia. |
| `--cache-path` | Custom path for the Yugipedia lookup cache JSON. |
| `--only-explicit-translated` | Only compare against Yugipedia's explicit `Translated Japanese name` (skip `English name` fallback). |
| `--ignore-case` | Perform case-insensitive name comparison. |
| `--reset-matching` | Reset `overriden_check` from `1` to `0` when `ocg_name` matches Yugipedia's translation. |
| `--report` | Write a full `.json` or `.csv` report of checked cards and statuses. |
| `--limit-preview` | Maximum sample updates to print in console output (default: `25`). |

---

## `audit_archetypes.py` (Archetype Exclusivity)

Validates bidirectional archetype exclusivity across **Master-format `cards.jsonl`** (not Rush Duel or GBA tables) using the **Smart First-Letter Case-Sensitive Rule**:
- Exact case-sensitive substring matching by default (`"HERO"` ≠ `"Hero"`, `"Xyz"` ≠ `"XYZ"`).
- Lowercase-initial archetype names (e.g., `"roid"`, `"tellarknight"`, `"verz"`) match both lowercase and capitalized first letters (`[Rr]oid`, `[Tt]ellarknight`, `[Vv]erz`).
- Turned-A (`Ɐ`, U+2C6F) normalizes to `A` for `atorakushon`, and wildcard numeric archetypes (`nanbaazu10x`, `kaosunanbaazu10x`) match `101`–`107`.
- Explicit rule-text exclusions (`(This card is not treated as a "<arch>" card.)` in `ocg_text`) are honored automatically so excluded false positives are not flagged as violations.

```bash
python audit_archetypes.py --format summary
python audit_archetypes.py --format md
python audit_archetypes.py --strict
```

---

## Testing

Run the isolated unit and integration test suite (covering `audit_archetypes.py`, `sync_db.py`, `apply_text_mod.py`, and OCG Standard DB Studio):

```bash
python -m unittest discover -s tests -v
```

---

## Credits & Acknowledgments

- **[Yugipedia](https://yugipedia.com/)**: Source for baseline card metadata, Konami Card Database IDs, Japanese readings, archetype/series classifications, and card text for Rush Duel, OCG-only, and retro game-only cards.
- **[Ultimate Card Text Mod by FoodUnderKeyboard](https://www.nexusmods.com/yugiohmasterduel/mods/2087)**: Source of the card text overhaul, including effect erratas, `① ② ③` effect numbering, and standard PSCT effect shortenings.
