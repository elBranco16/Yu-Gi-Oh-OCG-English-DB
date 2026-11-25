# DECISIONS.md — `ocg-standard-db` Precedents & Settled Rulings

Authoritative log of resolved translation edge cases, naming precedents, and policy rulings for `ocg-standard-db`. Agents must read this file at session start alongside `STATUS.md` so settled rulings stay consistent across batches.

## How to Use This File
- **Before asking the user** about a borderline naming or terminology choice, check whether a precedent already exists here.
- **When the user settles a new edge case** during a batch, append a new `DEC-###` entry below before closing the batch.
- **Superseding a ruling:** Never silently delete an old entry; mark it `Status: Superseded by DEC-###` and add the replacement entry so git history and rationale remain clear.

---

## Baseline Project Rulings

### DEC-001 — Tier 3 Furigana Uses Spoken Ruby Only (Never Combine Kanji + Ruby)
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `cards.jsonl`, `rush_cards.jsonl`, `gba_cards.jsonl` (`ocg_name`)
- **Ruling:** For both Tier 3 furigana categories, use only the spoken ruby layer and never combine kanji and ruby meanings into one bloated `ocg_name`:
  - **Pure-Japanese puns (`SPOKEN_FIRST`):** Translate the non-loanword spoken ruby meaning only.
  - **Coined katakana / portmanteau ruby (`Furigana-Primary`):** Use the coined katakana name only.
- **Examples:**
  - Pure-Japanese pun (`SPOKEN_FIRST`): `好敵手の記憶` (kanji: Rival / ruby: `とも` = Friend) → **Target (pending batch):** `Memory of a Friend` *(Current live DB `10297`: `Memory of an Adversary`)*.
  - Coined katakana (`Furigana-Primary`): `天霆號アーゼウス` (`ネガロギアアーゼウス`) → **Current:** `Negalogia AA-ZEUS` (not `Divine Arsenal AA-ZEUS - Sky Thunder`).

### DEC-002 — Unified `融合` / `フュージョン` Archetype Mapping
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `dump/archetypes.jsonl`, `dump/cards.jsonl`
- **Ruling:** Map `融合` and `フュージョン` to a single archetype (`yuugou_fyuujon` → `fusion`), matching both `Fusion` and `fusion` under `audit_archetypes.py --strict`. Preserve official TCG variants (`"Fusion; Polymerization"` on `yuugou_fyuujon` / `"Polymerization"` on card rows) in `tcg_name`.
- **Exception Note:** `"Fusion; Polymerization"` on `archetypes.archetype_id = 'yuugou_fyuujon'` is an intentional one-off semicolon-separated multi-variant `tcg_name` reflecting the TCG's split of a single OCG archetype.
- **Rationale:** Matches OCG mechanical equivalence without TCG's split between `Polymerization` and `Fusion`.

### DEC-003 — `デーモン` Archetype (`Daemon`) vs. `悪魔族` Race (`Demon`)
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `dump/archetypes.jsonl`, `dump/terms.jsonl`, `dump/cards.jsonl`, `ocg_text`
- **Ruling:** Translate the `デーモン` archetype uniformly as `Daemon` across every member (including legacy cards like `デーモンの召喚` → `Daemon's Summon` and `レッド・デーモンズ・ドラゴン` → `Red Daemon's Dragon`), and keep `悪魔族` as `Demon` (race) in `ocg_text`.
- **Rationale:** Eliminates retroactive TCG `Archfiend` and `(This card is always treated as...)` band-aids while preventing substring collisions between race names and archetype names.

### DEC-004 — Shared-Letter / Different-Ruby Archetype Splits
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `dump/archetypes.jsonl`, `dump/cards.jsonl`
- **Ruling:** Never leave colliding single-letter archetypes as bare letters. Expand them using their locked `dump/archetypes.jsonl` strings (`Ｃ` [`コクーン`] → `COCOON`, `Ｃ` [`チェーン`] → `CHAIN`, `Ｄ` [`ディフォーマー`] → `Deformer`, `Ｄ－ＨＥＲＯ` → `Destiny HERO`).
- **Rationale:** Preserves distinct OCG ruby-based archetype identities in English substring searches.

### DEC-005 — Official TCG Names as Starting Candidates
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** All `ocg_name` curations
- **Ruling:** Evaluate the official TCG name as a starting candidate: keep it when it is faithful to the OCG original and passes all rules; revise it for censorship, arbitrary renames (`Fierce Knight` for `暗黒騎士`), `Archfiend`-style band-aids, archetype integrity, or locked terminology.
- **Rationale:** Prevents unnecessary divergence on already-faithful translations while enforcing strict OCG accuracy where TCG localization drifted.

### DEC-006 — Display-Name Romanization (Characters & Untranslated Japanese Terms)
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `dump/characters.jsonl` (`ocg_name`) and untranslated Japanese terms in card, archetype, and series `ocg_name` values (subject to Priority 1 locked strings in `dump/archetypes.jsonl`)
- **Ruling:** Render Japanese personal names (Given-Family order) and untranslated Japanese words inside display names in Modified Hepburn without macrons:
  - **Long vowels:** `ou` → `o`, `oo` → `o`, `uu` → `u`, `aa` → `a`, `ii` → `i`, `ee` → `e`; keep `ei` as `ei`; render katakana `ー` as the matching single vowel (no macrons).
  - **Syllabic `ん`:** Always `n` before `b`/`m`/`p` (never `m`); insert apostrophe `n'` before vowels or `y` when syllable boundaries would otherwise be ambiguous.
  - **Small `っ` (sokuon):** Double the following consonant (`tt`, `kk`, `ss`, `pp`, etc.), using `cch` before `ch` (e.g., `Micchan`).
  - **Voiced kana `ぢ`/`づ`:** Render as `ji` / `zu`.
  - *(Internal `archetype_id` and `series_id` keys stay on their separate lowercase ASCII romaji slug convention that preserves `ou`/`uu` and doubles `ー`.)*
- **Examples:**
  - Characters: `Yugi Muto`, `Takuma Saio`, `Ryo Bakura`, `Asuka Tenjoin`, `Tatsuhisa Kamijo`, `Chikuzen Oka`, `Eiji Tsukinami`, `Gekko Tenma`, `Jun'ya Kakizoe`, `Miu Shiun'in`, `Allen Kozuki`.
  - Archetypes/cards: `剛鬼` → `Goki`, `忍法` → `Ninpo`, `竜華` → `Ryuge`, `妖仙獣` → `yosenju`.

### DEC-007 — Normal Monster Prose Flavor Text Review Boundary
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `ocg_text` on Normal Monsters (`cards.jsonl`, `rush_cards.jsonl`, `gba_cards.jsonl`)
- **Ruling:** Hold Normal Monster prose flavor text containing any prose word that overlaps a locked game term—both **legacy TCG** (`fairy`, `fiend`, `spell(s)`, `graveyard`, `zombie`, `tribute`, `pyro`, `aqua`, `banish`) and **migrated OCG** (`angel`, `demon`, `magic`, `cemetery`, `undead`, `release`, `flame`, `race`/`type`, `exclude`)—or Rush Duel series flavor references for case-by-case human approval. Mechanical `-Type` → `-Race` updates unambiguously referring to Monster Races may be applied automatically.

### DEC-008 — Paired Japanese Dashes Use Tight Paired Em Dashes (`—...—`)
- **Date:** 2026-11-25
- **Status:** Active (Target — pending migration batch; live DB currently has `0` em-dash cards and still uses legacy `- ... -`)
- **Scope:** `cards.jsonl`, `rush_cards.jsonl`, `gba_cards.jsonl` (`ocg_name`)
- **Ruling:** Translate Japanese paired dashes (`－...－`) into paired tight em dashes (`—...—`, with a space before the opening `—`, no inner spaces, and a trailing space after the closing `—` only when text follows such as a variant tag) rather than legacy paired hyphens (`- ... -`) or a single leading hyphen (` - ...`), unless `dump/archetypes.jsonl` locks a different substring.
- **Examples:**
  - `聖なるバリア －ミラーフォース－` → **Target (pending batch):** `Holy Barrier —Mirror Force—` *(Current live DB `4887`: `Holy Barrier - Mirror Force -`)*
  - `混沌帝龍 －終焉の使者－` → **Target (pending batch):** `Chaos Emperor Dragon —Envoy of the End—` *(Current live DB `5860`: `Chaos Emperor Dragon - Envoy of the End -`)*
  - Variant suffix example: `Holy Barrier —Mirror Force— (Tag Force Special)`

### DEC-009 — Final-Item `-Race` Suffixing Policy
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `ocg_text` (`cards.jsonl`, `rush_cards.jsonl`, `gba_cards.jsonl`)
- **Ruling:** Append `-Race` **only to the final race** in multi-race lists before `monster` and in `are <Race>` lists (e.g., `Beast-Warrior, Plant, Beast, and Insect-Race`, not `Beast-Warrior-Race, Plant-Race, Beast-Race, and Insect-Race`).
- **Rationale:** Matches natural English coordination while keeping OCG `種族` (`Race`) terminology consistent.

### DEC-010 — Hands-Off Ultimate Card Text Mod Prose & `Cemetery(ies)` Standardization
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `ocg_text` (`cards.jsonl`, `rush_cards.jsonl`, `gba_cards.jsonl`), `apply_text_mod.py`
- **Ruling:**
  - Do **not** rewrite, paraphrase, or restyle existing Ultimate Card Text Mod effect/ruling prose unless the user explicitly flags a discrepancy. Preserve existing `Select`/`Choose` non-targeting wording and `(s)` plural hedges in untouched mod text.
  - Standardize the plural-hedge form of `Cemetery` as **`Cemetery(ies)`** (migrated across all `23` existing Master cards and enforced in `apply_text_mod.py`, replacing legacy `Cemetery(s)`).
  - For **brand-new card text drafts**, use **`choose`** for non-targeting selection, allow mod-style **`(s)`** hedges (`monster(s)`, `card(s)`), and write **`Cemetery(ies)`** instead of `Cemetery(s)`.
- **Rationale:** Protects curated errata/PSCT precision while eliminating the ungrammatical `Cemetery(s)` artifact from mechanical `GY(s)` replacement.

### DEC-011 — Core OCG Terminology Authority (`dump/terms.jsonl`) & Katakana Loanword Safeguard
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `dump/terms.jsonl`, card `ocg_name` and `ocg_text`
- **Ruling:** `dump/terms.jsonl` is the single source of truth for core OCG game terms (`Magic`, `Cemetery`, `Exclude`, `Release`, `Advance Summon`, `Reverse`, `Race`, `Dual`, `FLAME`, `GOD`, `Demon`, `Angel`, `Magician`, `Undead`, `Flame`, `Water`, `Bird-Beast`, `Sea Dragon`, `Phantom Dragon`, `Phantom God Beast`, `Illusion Demon`, `Heaven Warrior`, `Old God`).
  - Apply locked `terms.jsonl` mappings **only when the Japanese source uses the underlying OCG term** (`魔法`, `天使`, `悪魔`, `アンデット`, `墓地`), **never** to literal katakana loanwords in card names (`フェアリー・ドラゴン` stays `Fairy Dragon`; `ゾンビキャリア` stays `Zombie Carrier`).
  - `FLAME Flame-Race` (`炎属性・炎族`) and `WATER Water-Race` (`水属性・水族`) are intentional.
  - `Reverse` / `Reverse Summon` applies strictly to `リバース` and `反転召喚`, never to generic `flip face-up`/`face-down` or coin/deck flips.
- **Rationale:** Prevents both TCG drift and over-eager English word replacement on katakana loanwords.

### DEC-012 — `overriden_check` Auto-Derived Yugipedia Divergence Flag
- **Date:** 2026-11-25
- **Status:** Active
- **Scope:** `cards.jsonl`, `rush_cards.jsonl`, `gba_cards.jsonl`, `sync_db.py`, DB Studio
- **Ruling:** `overriden_check = 1` indicates that `ocg_name` differs from Yugipedia's baseline translation (`0` = matches or unchecked default).
  - Maintained automatically by `python sync_db.py check` (which writes updates to `dump/*.jsonl` unless `--dry-run` or `--skip-yugipedia` is passed; pass `--reset-matching` to reset `1 → 0`) and by DB Studio Save & Export.
  - During offline `--skip-yugipedia` batches, agents also manually set `overriden_check = 1` when a curated `ocg_name` clearly diverges from Yugipedia; the next Yugipedia sync reconciles final status.
- **Rationale:** Eliminates the contradiction between manual-flag docs and automated Yugipedia diffing in `sync_db.py`.

---

## Batch Precedents

*(Append new batch-level rulings here using the template below.)*

<!--
### DEC-014 — <Short Descriptive Title>
- **Date:** YYYY-MM-DD
- **Status:** Active
- **Scope:** <Card IDs, archetype_id, or file(s)>
- **Ruling:** <Exact rule or chosen translation>
- **Rationale:** <Why this choice beat the alternatives>
- **Examples:** `<ja_base> (<ja_kana>)` → `<ocg_name>`
-->
