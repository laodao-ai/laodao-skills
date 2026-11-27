"""不联网、不需要 mlx-audio / playwright 的纯函数测试。

运行：python3 -m unittest discover -s video-fetch/tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch  # noqa: E402
import transcribe  # noqa: E402
from platforms import FetchError, bilibili, douyin  # noqa: E402

DY_SHARE = "5.12 复制打开抖音，看看【短耳兔AI的作品】5个AI交互动效提示词 https://v.douyin.com/xTMpUIFc6RM/ e@B.gO 10/03 YMw:/"


class ExtractUrl(unittest.TestCase):
    def test_share_text(self):
        self.assertEqual(fetch.extract_url(DY_SHARE), "https://v.douyin.com/xTMpUIFc6RM/")

    def test_plain_url(self):
        self.assertEqual(fetch.extract_url("https://www.bilibili.com/video/BV1fxu86uEVS/"),
                         "https://www.bilibili.com/video/BV1fxu86uEVS/")

    def test_no_url(self):
        self.assertIsNone(fetch.extract_url("没有链接"))


class Match(unittest.TestCase):
    def test_douyin(self):
        self.assertTrue(douyin.match("https://v.douyin.com/Sron2txr3Lg/"))
        self.assertTrue(douyin.match("https://www.douyin.com/video/7703213715362158075"))
        self.assertFalse(douyin.match("https://www.bilibili.com/video/BV1fxu86uEVS/"))
        self.assertFalse(douyin.match("https://example.com/douyin.com"))

    def test_bilibili(self):
        self.assertTrue(bilibili.match("https://www.bilibili.com/video/BV1fxu86uEVS/"))
        self.assertTrue(bilibili.match("https://b23.tv/xxxx"))
        self.assertFalse(bilibili.match("https://v.douyin.com/Sron2txr3Lg/"))
        self.assertFalse(bilibili.match("https://example.com/"))

    def test_find_platform(self):
        self.assertIs(fetch.find_platform("https://b23.tv/xxxx"), bilibili)
        self.assertIs(fetch.find_platform("https://v.douyin.com/Sron2txr3Lg/"), douyin)
        self.assertIsNone(fetch.find_platform("https://example.com/"))


class Ids(unittest.TestCase):
    def test_bv(self):
        self.assertEqual(bilibili.extract_bv("https://www.bilibili.com/video/BV1fxu86uEVS/?p=2"), "BV1fxu86uEVS")
        self.assertIsNone(bilibili.extract_bv("https://www.bilibili.com/read/cv123"))

    def test_bilibili_resolve_direct(self):
        self.assertEqual(bilibili.resolve("https://www.bilibili.com/video/BV1fxu86uEVS/?p=2"),
                         ("BV1fxu86uEVS", "https://www.bilibili.com/video/BV1fxu86uEVS/?p=2"))

    def test_douyin_resolve_direct(self):
        self.assertEqual(douyin.resolve("https://www.douyin.com/video/7703213715362158075"),
                         ("7703213715362158075", "https://www.douyin.com/video/7703213715362158075"))

    def test_douyin_note_rejected(self):
        with self.assertRaises(Exception) as cm:
            douyin.resolve("https://www.douyin.com/note/7703213715362158075")
        self.assertIn("图文", str(cm.exception))


class SplitLines(unittest.TestCase):
    def test_sentence_end(self):
        self.assertEqual(transcribe.split_lines("你好。今天天气不错！真的吗？"),
                         ["你好。", "今天天气不错！", "真的吗？"])

    def test_long_sentence_split_at_comma(self):
        text = "第一段比较长的内容在这里，第二段也比较长的内容在这里，第三段收尾。"
        lines = transcribe.split_lines(text)
        self.assertGreater(len(lines), 1)
        self.assertEqual("".join(lines), text)

    def test_punctuation_only_dropped(self):
        self.assertEqual(transcribe.split_lines("。。好的。"), ["好的。"])


class Ts(unittest.TestCase):
    def test_format(self):
        self.assertEqual(transcribe.ts(0), "00:00:00,000")
        self.assertEqual(transcribe.ts(3661.5), "01:01:01,500")
        self.assertEqual(transcribe.ts(59.9996), "00:01:00,000")


class Chunks(unittest.TestCase):
    def test_short_audio_single_chunk(self):
        self.assertEqual(transcribe.chunks(100.0, []), [(0.0, 100.0)])

    def test_cut_at_longest_pause(self):
        # 两个候选停顿，中点 90 与 120，取更长的那个
        gaps = [(89.0, 91.0), (119.0, 122.0)]
        plan = transcribe.chunks(200.0, gaps)
        self.assertEqual(plan[0], (0.0, 120.5))
        self.assertEqual(plan[-1][1], 200.0)

    def test_hard_cut_without_pause(self):
        plan = transcribe.chunks(400.0, [])
        self.assertEqual(plan, [(0.0, 150.0), (150.0, 300.0), (300.0, 400.0)])


class DouyinPlayable(unittest.TestCase):
    OK = {"aweme_type": 0, "images": None,
          "status": {"is_delete": False, "is_prohibited": False, "private_status": 0}}

    def test_normal_video_passes(self):
        douyin.check_playable(self.OK)

    def test_deleted(self):
        with self.assertRaises(FetchError):
            douyin.check_playable({**self.OK, "status": {"is_delete": True}})

    def test_private(self):
        with self.assertRaises(FetchError):
            douyin.check_playable({**self.OK, "status": {"private_status": 1}})

    def test_image_post(self):
        with self.assertRaises(FetchError):
            douyin.check_playable({**self.OK, "aweme_type": 68})
        with self.assertRaises(FetchError):
            douyin.check_playable({**self.OK, "images": [{"url_list": ["x"]}]})


if __name__ == "__main__":
    unittest.main()
