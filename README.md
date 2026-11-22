# Yu-Gi-Oh! OCG Standard Database

A collaborative, Git-friendly Master OCG Standard database covering Yu-Gi-Oh! cards (OCG, Rush Duel, and game-only), archetypes, thematic series, characters, and core terminology.

All tables are stored as deterministic, primary-key-sorted **JSON Lines (`dump/*.jsonl`)** alongside `dump/schema.sql`, and can be rebuilt into `ocg_standard.db` on demand with `sync_db.py`.

---

## Repository Structure

```text
.
├── sync_db.py                  # Export/import/validate between SQLite and dump/
├── apply_text_mod.py           # Populate/update ocg_text & en_legacy_names (erratas, numbering, PSCT shortening, OCG localization)
└── dump/
    ├── schema.sql              # Exact SQLite table & index definitions
    ├── cards.jsonl             # 17,728 cards (OCG, Rush Duel, game-only)
    ├── archetypes.jsonl        # 771 official OCG archetypes
    ├── series.jsonl            # 369 thematic series
    ├── card_archetypes.jsonl   # 10,622 card <-> archetype links
    ├── card_series.jsonl       # 3,695 card <-> series links
    ├── characters.jsonl        # 1,868 characters
    └── terms.jsonl             # 88 core OCG terminology entries
```

---

## Schema & Data Conventions

| Table | Columns |
| :--- | :--- |
| `cards` | `id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name`, `en_legacy_names`, `ocg_text`, `overriden_check` |
| `archetypes` | `archetype_id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name`, `strict_negative_check` |
| `series` | `series_id`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_name` |
| `card_archetypes` | `card_id`, `archetype_id`, `is_rule_override` |
| `card_series` | `card_id`, `series_id` |
| `characters` | `character_id`, `series`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_dub_name` |
| `terms` | `term_id`, `category`, `ja_base`, `ja_kana`, `ocg_name`, `tcg_en`, `en_legacy_terms` |

### Key Conventions
- **Card IDs (`cards.id`):** Uses the official Konami Card Database ID (`cid`, e.g., `4007` for *Blue-Eyes White Dragon*, `15150` for *Sevens Road Magician*). Cards without a Konami `cid` (such as retro game-only cards, Tokens, or alternate variants) use sequential IDs starting at `900001`.
- **Japanese Names (`ja_base` / `ja_kana`):** `ja_kana` stores the reading/kana; `ja_base` is `null` whenever the name has no kanji and would be identical to `ja_kana`.
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
| `python sync_db.py check` | Validates all `dump/*.jsonl` files in a temporary SQLite DB (JSON syntax, primary keys, foreign keys, and integrity) without touching any local `.db`. |
| `python sync_db.py import` | Rebuilds `./ocg_standard.db` from `dump/`. Supports `--db <path>`. |
| `python sync_db.py export` | Exports `./ocg_standard.db` back into sorted, UTF-8/LF `dump/*.jsonl` files and `dump/schema.sql`. Supports `--db <path>`. |

---

## Credits & Acknowledgments

- **[Yugipedia](https://yugipedia.com/)**: Source for baseline card metadata, Konami Card Database IDs, Japanese readings, archetype/series classifications, and card text for Rush Duel, OCG-only, and retro game-only cards.
- **[Ultimate Card Text Mod by FoodUnderKeyboard](https://www.nexusmods.com/yugiohmasterduel/mods/2087)**: Source of the card text overhaul, including effect erratas, `① ② ③` effect numbering, and standard PSCT effect shortenings.
