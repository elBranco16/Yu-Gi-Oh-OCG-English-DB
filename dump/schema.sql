CREATE TABLE "archetypes" (
                        archetype_id TEXT PRIMARY KEY,
                        ja_base TEXT,
                        ja_kana TEXT,
                        ocg_name TEXT NOT NULL,
                        tcg_name TEXT NOT NULL,
                        strict_negative_check INTEGER DEFAULT 0
                    );

CREATE TABLE card_archetypes (
                card_id INTEGER NOT NULL,
                archetype_id TEXT NOT NULL,
                is_rule_override INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (card_id, archetype_id),
                FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
                FOREIGN KEY (archetype_id) REFERENCES archetypes(archetype_id) ON DELETE CASCADE
            );

CREATE TABLE card_series (
                card_id INTEGER NOT NULL,
                series_id TEXT NOT NULL,
                PRIMARY KEY (card_id, series_id),
                FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
                FOREIGN KEY (series_id) REFERENCES series(series_id) ON DELETE CASCADE
            );

CREATE TABLE "cards" (
                        id INTEGER PRIMARY KEY,
                        ja_base TEXT,
                        ja_kana TEXT,
                        ocg_name TEXT NOT NULL UNIQUE,
                        tcg_name TEXT,
                        en_legacy_names TEXT,
                        ocg_text TEXT,
                        overriden_check INTEGER NOT NULL DEFAULT 0
                    );

CREATE TABLE characters (
                character_id TEXT PRIMARY KEY,
                series TEXT NOT NULL,
                ja_base TEXT,
                ja_kana TEXT,
                ocg_name TEXT NOT NULL,
                tcg_dub_name TEXT
            );

CREATE TABLE series (
            series_id TEXT PRIMARY KEY,
            ja_base TEXT,
            ja_kana TEXT,
            ocg_name TEXT NOT NULL,
            tcg_name TEXT NOT NULL
        );

CREATE TABLE "terms" (
                        term_id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        ja_base TEXT,
                        ja_kana TEXT,
                        ocg_name TEXT NOT NULL,
                        tcg_en TEXT,
                        en_legacy_terms TEXT
                    );

-- === INDEXES / TRIGGERS / VIEWS ===

CREATE INDEX idx_card_archetypes_arch ON card_archetypes(archetype_id);

CREATE INDEX idx_card_series_card ON card_series(card_id);

CREATE INDEX idx_card_series_series ON card_series(series_id);

CREATE INDEX idx_cards_en_legacy ON cards(en_legacy_names);

CREATE INDEX idx_cards_ja_base ON cards(ja_base);

CREATE INDEX idx_cards_ocg_name ON cards(ocg_name);

CREATE INDEX idx_cards_tcg_name ON cards(tcg_name);

CREATE INDEX idx_characters_ocg_name ON characters(ocg_name);

CREATE INDEX idx_characters_series ON characters(series);

CREATE INDEX idx_series_ocg_name ON series(ocg_name);

CREATE INDEX idx_series_tcg_name ON series(tcg_name);

CREATE INDEX idx_terms_category ON terms(category);

CREATE INDEX idx_terms_en_legacy ON terms(en_legacy_terms);

CREATE INDEX idx_terms_ocg_name ON terms(ocg_name);
