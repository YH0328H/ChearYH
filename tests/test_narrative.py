import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.narrative import NarrativeConfig, NarrativeError, generate_narrative, load_narrative_config  # noqa: E402

CFG = NarrativeConfig(base_url="https://x.test/v1", model_id="m-1", api_key="k-test")


def reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class NarrativeTests(unittest.TestCase):
    def test_generate_narrative_returns_structured_result(self) -> None:
        seen = []

        def post(url, body, headers):
            seen.append((url, body["model"]))
            return reply('{"narrative": "用户问了工作的事", "emotion_tag": "calm", "relation_tag": "user"}')

        result = generate_narrative(CFG, ["用户: 最近工作怎么样?", "我: 还行"], post)
        self.assertEqual(result["narrative"], "用户问了工作的事")
        self.assertEqual(result["emotion_tag"], "calm")
        self.assertEqual(result["relation_tag"], "user")
        self.assertEqual(seen, [("https://x.test/v1/chat/completions", "m-1")])

    def test_missing_key_raises(self) -> None:
        cfg = NarrativeConfig(CFG.base_url, CFG.model_id, "")
        with self.assertRaises(NarrativeError):
            generate_narrative(cfg, ["test"], lambda u, b, h: reply("{}"))

    def test_bad_json_raises(self) -> None:
        with self.assertRaises(NarrativeError):
            generate_narrative(CFG, ["test"], lambda u, b, h: reply("not json"))

    def test_empty_content_raises(self) -> None:
        with self.assertRaises(NarrativeError):
            generate_narrative(CFG, ["test"], lambda u, b, h: reply(""))

    def test_load_config_reads_key_from_environment(self) -> None:
        path = Path(tempfile.mkdtemp()) / "narrative.toml"
        path.write_text(
            '[narrative]\nbase_url = "https://y.test"\nmodel_id = "m-2"\nkey_env = "CETHER_TEST_KEY"\n',
            encoding="utf-8",
        )
        cfg = load_narrative_config(path, {"CETHER_TEST_KEY": "k-env"})
        self.assertEqual((cfg.base_url, cfg.model_id, cfg.api_key), ("https://y.test", "m-2", "k-env"))


if __name__ == "__main__":
    unittest.main()
