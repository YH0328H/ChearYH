import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.vision import VisionConfig, VisionError, build_request, describe  # noqa: E402

CFG = VisionConfig(base_url="https://api.example.test/v1/", model_id="deepseek-v4.1-flash", api_key="k-test")
PNG = b"\x89PNG\r\n\x1a\nfake"


def reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class VisionTests(unittest.TestCase):
    def test_request_carries_model_key_and_inline_image(self) -> None:
        url, body, headers = build_request(CFG, PNG)
        self.assertEqual(url, "https://api.example.test/v1/chat/completions")
        self.assertEqual(body["model"], "deepseek-v4.1-flash")
        self.assertEqual(headers["Authorization"], "Bearer k-test")
        image = body["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image.startswith("data:image/png;base64,"))

    def test_describe_returns_trimmed_text(self) -> None:
        seen = {}

        def post(url, body, headers):
            seen["url"] = url
            return reply("  一个代码编辑器  ")

        self.assertEqual(describe(CFG, PNG, post), "一个代码编辑器")
        self.assertTrue(seen["url"].endswith("/chat/completions"))

    def test_bad_shape_raises(self) -> None:
        with self.assertRaises(VisionError):
            describe(CFG, PNG, lambda u, b, h: {"error": "nope"})

    def test_empty_text_raises(self) -> None:
        with self.assertRaises(VisionError):
            describe(CFG, PNG, lambda u, b, h: reply("   "))

    def test_missing_key_raises_before_post(self) -> None:
        called = []
        cfg = VisionConfig(CFG.base_url, CFG.model_id, "")
        with self.assertRaises(VisionError):
            describe(cfg, PNG, lambda u, b, h: called.append(1) or reply("x"))
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
