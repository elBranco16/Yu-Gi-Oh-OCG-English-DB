"""Isolated regression tests for audit_archetypes.py matching and audit logic."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_archetypes as aa


def _card(
    cid: int,
    ocg_name: str,
    *,
    ja_base: str | None = None,
    ja_kana: str = "テスト",
    tcg_name: str | None = None,
    ocg_text: str | None = None,
) -> dict:
    return {
        "id": cid,
        "ja_base": ja_base,
        "ja_kana": ja_kana,
        "ocg_name": ocg_name,
        "tcg_name": tcg_name,
        "en_legacy_names": None,
        "ocg_text": ocg_text,
        "overriden_check": 0,
    }


def _arch(
    archetype_id: str,
    ocg_name: str,
    *,
    ja_base: str | None = None,
    ja_kana: str = "テスト",
    tcg_name: str | None = None,
) -> dict:
    return {
        "archetype_id": archetype_id,
        "ja_base": ja_base,
        "ja_kana": ja_kana,
        "ocg_name": ocg_name,
        "tcg_name": tcg_name,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class MatchArchetypeTests(unittest.TestCase):
    def test_smart_case_sensitive_uppercase_archetypes(self) -> None:
        self.assertTrue(aa.match_archetype("HERO", "Elemental HERO Neos", "hiiroo"))
        self.assertFalse(aa.match_archetype("HERO", "A Hero Emerges", "hiiroo"))
        self.assertTrue(aa.match_archetype("Xyz", "Xyz Reborn", "ekushiizu"))
        self.assertFalse(aa.match_archetype("Xyz", "XYZ-Dragon Cannon", "ekushiizu"))
        self.assertFalse(aa.match_archetype("CHAIN", "Chain Disappearance", "cheen"))

    def test_lowercase_initial_archetypes_match_both_cases(self) -> None:
        self.assertTrue(aa.match_archetype("roid", "Speedroid Terrortop", "roido"))
        self.assertTrue(aa.match_archetype("roid", "Roid Connection Zone", "roido"))
        self.assertFalse(aa.match_archetype("roid", "Artificial Human - Psycho Shocker", "roido"))
        self.assertTrue(aa.match_archetype("fusion", "Deathtoy Fusion", "yuugou_fyuujon"))
        self.assertTrue(aa.match_archetype("fusion", "Overfusion", "yuugou_fyuujon"))
        self.assertTrue(aa.match_archetype("fusion", "Fusion Destiny", "yuugou_fyuujon"))

    def test_numbers_10x_special_matchers(self) -> None:
        for num in range(101, 108):
            self.assertTrue(
                aa.match_archetype("Numbers 10X", f"Numbers {num}: Silent Honors Ark Knight", "nanbaazu10x")
            )
            self.assertTrue(
                aa.match_archetype(
                    "Chaos Numbers 10X", f"Chaos Numbers {num}: Silent Honors Dark Knight", "kaosunanbaazu10x"
                )
            )
        for bad in (100, 108, 109, 1010, 1070):
            self.assertFalse(aa.match_archetype("Numbers 10X", f"Numbers {bad}: Example", "nanbaazu10x"))
            self.assertFalse(
                aa.match_archetype("Chaos Numbers 10X", f"Chaos Numbers {bad}: Example", "kaosunanbaazu10x")
            )

    def test_atorakushon_turned_a_normalization(self) -> None:
        self.assertTrue(
            aa.match_archetype("Attraction", "Amaze \u2c6fttraction Cyclone Coaster", "atorakushon")
        )
        # Non-atorakushon archetypes do not normalize turned-A
        self.assertFalse(aa.match_archetype("Attraction", "Amaze \u2c6fttraction Cyclone Coaster", "other"))


class RuleExclusionTests(unittest.TestCase):
    def test_single_and_article_variants(self) -> None:
        self.assertTrue(
            aa.has_rule_exclusion("ritua", '(This card is not treated as a "Ritua" card.)')
        )
        self.assertTrue(
            aa.has_rule_exclusion("ritua", '(This card is not treated as a "ritua" card.)')
        )
        self.assertTrue(
            aa.has_rule_exclusion("Angel", '(This card is not treated as an "Angel" card.)')
        )
        self.assertFalse(
            aa.has_rule_exclusion("ritua", 'Special Summon 1 "Ritua" monster from your Deck.')
        )

    def test_multi_archetype_exclusion_clauses(self) -> None:
        text = '(This card is not treated as a "Ritua" or "Daemon" card.)'
        self.assertTrue(aa.has_rule_exclusion("ritua", text))
        self.assertTrue(aa.has_rule_exclusion("Daemon", text))
        self.assertFalse(aa.has_rule_exclusion("HERO", text))

        text_three = '(This card is not treated as an "Alpha", "Beta", or "Gamma" card.)'
        self.assertTrue(aa.has_rule_exclusion("Alpha", text_three))
        self.assertTrue(aa.has_rule_exclusion("Beta", text_three))
        self.assertTrue(aa.has_rule_exclusion("Gamma", text_three))


class RunAuditTests(unittest.TestCase):
    def test_clean_fixture_has_zero_strict_violations(self) -> None:
        archetypes = [
            _arch("hiiroo", "HERO", ja_base="ＨＥＲＯ", ja_kana="ヒーロー"),
            _arch("roido", "roid", ja_kana="ロイド"),
        ]
        cards = [
            _card(4007, "Elemental HERO Neos", ja_base="Ｅ・ＨＥＲＯ ネオス", ja_kana="エレメンタルヒーロー ネオス"),
            _card(5915, "A Hero Emerges", ja_base="ヒーロー見参", ja_kana="ヒーローけんざん"),
            _card(6001, "Speedroid Terrortop", ja_kana="スピードロイド"),
            _card(6002, "Nexus Android", ocg_text='(This card is not treated as a "roid" card.)'),
        ]
        links = [
            {"card_id": 4007, "archetype_id": "hiiroo", "is_rule_override": 0},
            {"card_id": 6001, "archetype_id": "roido", "is_rule_override": 0},
        ]

        report = aa.run_audit(cards, archetypes, links)
        self.assertEqual(report["counts"]["strict_violations"], 0)
        self.assertEqual(report["counts"]["fp_pairs_total"], 0)
        self.assertEqual(report["counts"]["fn_pairs_total"], 0)
        self.assertEqual(report["counts"]["rule_excluded_pairs"], 1)

    def test_false_positives_and_pool_classification(self) -> None:
        archetypes = [_arch("roido", "roid", ja_kana="ロイド")]
        cards = [
            _card(5000, "Rogue Android", ja_kana="ローグ・ロイド"),  # OCG + JA_MATCH
            _card(3500, "Retro Android", ja_kana="レトロ"),          # VG
            _card(900001, "Variant Android", ja_kana="バリアント"),   # VG
            _card(7000, "Android Token", ja_kana="トークン"),         # TOKEN
        ]

        report = aa.run_audit(cards, archetypes, [])
        c = report["counts"]
        self.assertEqual(c["strict_violations"], 1)
        self.assertEqual(c["fp_archetypes"], 1)
        self.assertEqual(c["fp_pairs_total"], 4)
        self.assertEqual(c["fp_pairs_ocg"], 1)
        self.assertEqual(c["fp_pairs_vg"], 2)
        self.assertEqual(c["fp_pairs_token"], 1)
        self.assertEqual(c["fp_pairs_ja_match"], 1)

    def test_false_negatives_and_rule_override(self) -> None:
        archetypes = [_arch("deemon", "Daemon", ja_kana="デーモン")]
        cards = [
            _card(4028, "Summoned Skull", ja_kana="デーモンの召喚"),
            _card(4029, "Axe of Despair", ja_kana="デーモンの斧"),
        ]
        links = [
            {"card_id": 4028, "archetype_id": "deemon", "is_rule_override": 0},
            {"card_id": 4029, "archetype_id": "deemon", "is_rule_override": 1},
        ]

        report = aa.run_audit(cards, archetypes, links)
        self.assertEqual(report["counts"]["strict_violations"], 1)
        self.assertEqual(report["counts"]["fn_pairs_total"], 1)
        self.assertEqual(report["false_negatives"][0]["misses"][0]["id"], 4028)

    def test_allowed_arch_overlaps_vs_disallowed_overlaps(self) -> None:
        archetypes = [
            _arch("baaningunakkuru", "Burning Knuckle", ja_kana="バーニングナックル"),
            _arch("baaningunakkuraa", "Burning Knuckler", ja_kana="バーニングナックラー"),
            _arch("foo", "Star", ja_kana="ほし"),
            _arch("bar", "Starlight", ja_kana="こうせい"),
        ]
        cards = [
            _card(10001, "Burning Knuckle Cross Counter"),
            _card(10002, "Burning Knuckler Leadblow"),
            _card(10003, "Star Dragon"),
            _card(10004, "Starlight Road"),
        ]
        links = [
            {"card_id": 10001, "archetype_id": "baaningunakkuru", "is_rule_override": 0},
            {"card_id": 10002, "archetype_id": "baaningunakkuraa", "is_rule_override": 0},
            {"card_id": 10003, "archetype_id": "foo", "is_rule_override": 0},
            {"card_id": 10004, "archetype_id": "bar", "is_rule_override": 0},
        ]

        report = aa.run_audit(cards, archetypes, links)
        # Burning Knuckle -> Burning Knuckler is explicitly allowed (no FP, no arch_overlap)
        fp_ids = {row["archetype_id"] for row in report["false_positives"]}
        self.assertNotIn("baaningunakkuru", fp_ids)
        self.assertIn("foo", fp_ids)

        overlap_pairs = {(row["outer_id"], row["inner_id"]) for row in report["arch_overlaps"]}
        self.assertNotIn(("baaningunakkuru", "baaningunakkuraa"), overlap_pairs)
        self.assertIn(("foo", "bar"), overlap_pairs)

    def test_mixed_case_candidate_detection(self) -> None:
        archetypes = [_arch("saber", "Saber", ja_kana="セイバー")]
        cards = [
            _card(11001, "X-Saber Airbellum"),
            _card(11002, "Lightsaber Warrior"),
            _card(11003, "Nonmember lightsaber"),
        ]
        links = [
            {"card_id": 11001, "archetype_id": "saber", "is_rule_override": 0},
            {"card_id": 11002, "archetype_id": "saber", "is_rule_override": 0},
        ]

        report = aa.run_audit(cards, archetypes, links)
        self.assertEqual(report["counts"]["mixed_case_candidates"], 1)
        cand = report["mixed_case"][0]
        self.assertEqual(cand["proposed_ocg_name"], "saber")
        self.assertEqual(cand["exact_member_count"], 1)
        self.assertEqual(cand["lower_member_count"], 1)
        self.assertEqual(cand["extra_fp_count"], 1)

    def test_cli_strict_exit_codes_and_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = Path(tmp)
            _write_jsonl(dump_dir / "archetypes.jsonl", [_arch("hiiroo", "HERO", ja_base="ＨＥＲＯ", ja_kana="ヒーロー")])
            _write_jsonl(dump_dir / "cards.jsonl", [_card(4007, "Elemental HERO Neos")])
            _write_jsonl(
                dump_dir / "card_archetypes.jsonl",
                [{"card_id": 4007, "archetype_id": "hiiroo", "is_rule_override": 0}],
            )

            # Clean run exits normally (no SystemExit) and produces valid JSON
            out_json = dump_dir / "report.json"
            with (
                mock.patch.object(aa, "DUMP_DIR", dump_dir),
                mock.patch.object(
                    sys, "argv", ["audit_archetypes.py", "--strict", "--format", "json", "--out", str(out_json)]
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                aa.main()
            parsed = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(parsed["counts"]["strict_violations"], 0)

            # Add an unlinked colliding card -> --strict exits with code 1
            _write_jsonl(
                dump_dir / "cards.jsonl",
                [_card(4007, "Elemental HERO Neos"), _card(4008, "Rogue HERO")],
            )
            buf = io.StringIO()
            with (
                mock.patch.object(aa, "DUMP_DIR", dump_dir),
                mock.patch.object(sys, "argv", ["audit_archetypes.py", "--strict", "--format", "md"]),
                contextlib.redirect_stdout(buf),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    aa.main()
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("Rogue HERO", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
