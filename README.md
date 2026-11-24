# Yu-Gi-Oh! OCG Standard Database

A collaborative, Git-friendly Master OCG Standard database covering Yu-Gi-Oh! cards (OCG, Rush Duel, and game-only), archetypes, thematic series, characters, and core terminology.

All tables are stored as deterministic, primary-key-sorted **JSON Lines (`dump/*.jsonl`)** alongside `dump/schema.sql`, and can be rebuilt into `ocg_standard.db` on demand with `sync_db.py`.

---

## Repository Structure

```text
.
├── sync_db.py                  # Export/import/validate between SQLite and dump/, plus Yugipedia overriden_check verification
├── apply_text_mod.py           # Populate/update ocg_text & en_legacy_names (erratas, numbering, PSCT shortening, OCG localization)
├── audit_archetypes.py         # Bidirectional archetype exclusivity & false-negative auditor
└── dump/
    ├── schema.sql              # Exact SQLite table & index definitions
    ├── cards.jsonl             # 14,975 Master-format cards (OCG, game-only, Tokens)
    ├── rush_cards.jsonl        # 2,839 Rush Duel cards
    ├── gba_cards.jsonl         # 28 GBA-exclusive DM7/DM8 non-OCG cards
    ├── archetypes.jsonl        # 614 official OCG archetypes
    ├── series.jsonl            # 369 thematic series
    ├── card_archetypes.jsonl   # 10,077 Master card <-> archetype links
    ├── card_series.jsonl       # 2,049 Master card <-> series links
    ├── rush_card_series.jsonl  # 1,943 Rush card <-> series links
    ├── characters.jsonl        # 1,548 characters
    └── terms.jsonl             # 24 core OCG terminology entries
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
- **Card IDs (`cards.id` / `gba_cards.id`):** Uses the official Konami Card Database ID (`cid`, e.g., `4007` for *Blue-Eyes White Dragon*, `15150` for *Sevens Road Magician*) as well as `< 4007` retro/video-game IDs. Cards without a Konami `cid` or whose `< 4007` slot is occupied (such as Tokens or older game variants) use sequential IDs starting at `900001`. Standalone `gba_cards.id` uses the official in-game DM7 card number with DM8 fallback (`110`–`898`).
- **Japanese Names (`ja_base` / `ja_kana`):** `ja_kana` stores the reading/kana; `ja_base` is `null` whenever the name has no kanji and would be identical to `ja_kana`. `gba_cards` preserves verbatim GBA in-game Japanese spelling in `ja_base` (`null` when pure kana).
- **TCG Divergence (`tcg_name`):** Populated only when the TCG card name differs from `ocg_name`; otherwise `null`. Alternate official/game name variants (e.g., `#1` punctuation differences) are merged into `en_legacy_names` (`; `-separated).
- **Card Text Formatting (`ocg_text`):** Combines official/community effect erratas, `① ② ③` effect numbering, standard PSCT shortenings, and full OCG card/archetype/terminology localization (`terms.jsonl`). Rush Duel cards preserve `[Requirement]` / `[Effect]` blocks.
- **Manual Overrides (`overriden_check`):** `1` marks a curated/overridden card entry; `0` is default.

---

## Requirements

- **Python 3.10+** (standard library only — no `pip install` needed).

---

## Editing Workflow

### Option A: Edit `dump/*.jsonl` Directly (Recommended for Quick Edits)
```bash
git pull
# Edit dump/*.jsonl in VS Code or any UTF-8 text editor
python sync_db.py check        # Verify valid JSON, foreign keys, and SQLite integrity
git add dump/
git commit -m "Describe your edits"
git pull --rebase
git push
```

### Option B: Edit Visually in DB Browser for SQLite
```bash
git pull
python sync_db.py import       # Builds a local ocg_standard.db (ignored by Git)
# Open and edit ocg_standard.db in DB Browser for SQLite, then SAVE and CLOSE it
python sync_db.py export       # Exports your changes back to dump/*.jsonl
git diff                       # Optional: review exact row-level changes
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
| `python sync_db.py check` | Checks `cards.jsonl`, `rush_cards.jsonl`, and `gba_cards.jsonl` against Yugipedia's Japanese name translations (marking `ocg_name` mismatches with `overriden_check = 1`, cached in `.cache/yugipedia_translations_cache.json`), and validates all `dump/*.jsonl` files in a temporary SQLite DB (JSON syntax, primary keys, foreign keys, and integrity). |
| `python sync_db.py import` | Rebuilds `./ocg_standard.db` from `dump/`. Supports `--db <path>`. |
| `python sync_db.py export` | Exports `./ocg_standard.db` back into sorted, UTF-8/LF `dump/*.jsonl` files and `dump/schema.sql`. Supports `--db <path>`. |

### `sync_db.py check` Options

```bash
python sync_db.py check --dry-run            # Preview overriden_check changes without modifying dump/*.jsonl
python sync_db.py check --sync-db            # Also rebuild ocg_standard.db if dump/*.jsonl was updated
python sync_db.py check --skip-yugipedia     # Run offline JSONL/SQLite validation only
```

| Flag | Description |
| :--- | :--- |
| `--dry-run` | Preview `overriden_check` changes without modifying `dump/*.jsonl`. |
| `--sync-db` | Rebuild `--db` via `import` automatically if `dump/*.jsonl` was updated. |
| `--skip-yugipedia` | Skip the Yugipedia lookup pass and run offline JSONL/SQLite validation only. |
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

Validates bidirectional archetype exclusivity across Master-format `cards.jsonl` using the **Smart First-Letter Case-Sensitive Rule**:
- Exact case-sensitive substring matching by default (`"HERO"` ≠ `"Hero"`, `"Xyz"` ≠ `"XYZ"`).
- Lowercase-initial archetype names (e.g., `"roid"`, `"tellarknight"`, `"verz"`) match both lowercase and capitalized first letters (`[Rr]oid`, `[Tt]ellarknight`, `[Vv]erz`).
- Turned-A (`Ɐ`, U+2C6F) normalizes to `A` for `attraction`, and wildcard numeric archetypes (`number_10x`, `number_c10x`) match `101`–`107`.

```bash
python audit_archetypes.py --format summary
python audit_archetypes.py --format md
python audit_archetypes.py --strict
```

---

## Credits & Acknowledgments

- **[Yugipedia](https://yugipedia.com/)**: Source for baseline card metadata, Konami Card Database IDs, Japanese readings, archetype/series classifications, and card text for Rush Duel, OCG-only, and retro game-only cards.
- **[Ultimate Card Text Mod by FoodUnderKeyboard](https://www.nexusmods.com/yugiohmasterduel/mods/2087)**: Source of the card text overhaul, including effect erratas, `① ② ③` effect numbering, and standard PSCT effect shortenings.
