"""不联网、不需要 mlx-audio / playwright 的纯函数测试。

运行：python3 -m unittest discover -s video-fetch/tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch  # noqa: E402
import transcribe  # noqa: E402
from platforms import FetchError, bilibili, douyin, xiaohongshu, youtube  # noqa: E402

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

    def test_xiaohongshu(self):
        self.assertTrue(xiaohongshu.match(XHS_URL))
        self.assertFalse(xiaohongshu.match("https://v.douyin.com/Sron2txr3Lg/"))
        self.assertFalse(xiaohongshu.match("https://example.com/xiaohongshu.com"))

    def test_youtube(self):
        for url in ["https://www.youtube.com/watch?v=jNQXAC9IVRw", "https://youtube.com/shorts/jNQXAC9IVRw",
                    "https://m.youtube.com/watch?v=jNQXAC9IVRw", "https://youtu.be/jNQXAC9IVRw"]:
            self.assertTrue(youtube.match(url), url)
        self.assertFalse(youtube.match("https://example.com/youtube.com"))
        self.assertFalse(youtube.match("https://notyoutube.com/watch?v=jNQXAC9IVRw"))
        self.assertFalse(youtube.match("https://www.bilibili.com/video/BV1fxu86uEVS/"))
        self.assertIs(fetch.find_platform("https://youtu.be/jNQXAC9IVRw"), youtube)

    def test_find_platform(self):
        self.assertIs(fetch.find_platform("https://b23.tv/xxxx"), bilibili)
        self.assertIs(fetch.find_platform("https://v.douyin.com/Sron2txr3Lg/"), douyin)
        self.assertIsNone(fetch.find_platform("https://example.com/"))


XHS_URL = ("https://www.xiaohongshu.com/explore/6a672b100000000001000161"
           "?xsec_token=FAKE-token-for-tests=&xsec_source=app_share")


class Xiaohongshu(unittest.TestCase):
    def test_resolve_keeps_token(self):
        note_id, canonical = xiaohongshu.resolve(XHS_URL)
        self.assertEqual(note_id, "6a672b100000000001000161")
        self.assertIn("xsec_token=FAKE-token-for-tests", canonical)

    def test_discovery_item_path(self):
        url = XHS_URL.replace("/explore/", "/discovery/item/")
        self.assertEqual(xiaohongshu.resolve(url)[0], "6a672b100000000001000161")

    def test_missing_token_rejected(self):
        with self.assertRaises(FetchError):
            xiaohongshu.resolve("https://www.xiaohongshu.com/explore/6a672b100000000001000161")

    def test_share_text_extracts_full_url(self):
        text = "终于把自媒体起号skill搭建成功了 " + XHS_URL + " 复制后打开【小红书】查看笔记！"
        self.assertEqual(fetch.extract_url(text), XHS_URL)
        self.assertIs(fetch.find_platform(XHS_URL), xiaohongshu)


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


class YoutubeResolve(unittest.TestCase):
    VID = "jNQXAC9IVRw"
    CANON = f"https://www.youtube.com/watch?v={VID}"

    def test_four_forms(self):
        for url in [f"https://www.youtube.com/watch?v={self.VID}&t=10s", f"https://www.youtube.com/shorts/{self.VID}",
                    f"https://www.youtube.com/live/{self.VID}?feature=share", f"https://youtu.be/{self.VID}?si=abc"]:
            self.assertEqual(youtube.resolve(url), (self.VID, self.CANON), url)

    def test_unsupported(self):
        for url in ["https://www.youtube.com/@somechannel", "https://www.youtube.com/playlist?list=PLabc",
                    "https://www.youtube.com/watch?v=short", "https://www.youtube.com/watch", "https://youtu.be/"]:
            with self.assertRaises(FetchError, msg=url):
                youtube.resolve(url)


class Language(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(fetch.language_name("en"), "English")
        self.assertEqual(fetch.language_name("en-US"), "English")
        self.assertEqual(fetch.language_name("zh-Hans"), "Chinese")
        self.assertEqual(fetch.language_name("yue"), "Cantonese")

    def test_name_and_unknown_passthrough(self):
        self.assertEqual(fetch.language_name("English"), "English")
        self.assertEqual(fetch.language_name("German"), "German")

    def test_priority(self):
        self.assertEqual(fetch.pick_language("ja", "en"), "Japanese")
        self.assertEqual(fetch.pick_language(None, "en"), "English")
        self.assertEqual(fetch.pick_language(None, None), "Chinese")


class SplitLinesEnglish(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(transcribe.split_lines("Hello there. How are you?", "English"),
                         ["Hello there.", "How are you?"])

    def test_comma_split(self):
        text = "When we started the work we had no clue, and then everything changed quickly."
        lines = transcribe.split_lines(text, "English")
        self.assertEqual(lines, ["When we started the work we had no clue,", "and then everything changed quickly."])

    def test_long_no_comma_wraps_by_words(self):
        text = "this is a very long sentence without any commas that keeps going and going until it must wrap"
        lines = transcribe.split_lines(text, "English")
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(l) <= 42 for l in lines))
        self.assertEqual(" ".join(lines), text)

    def test_decimal_not_split(self):
        self.assertEqual(transcribe.split_lines("It costs 3.5 dollars.", "English"), ["It costs 3.5 dollars."])

    def test_chinese_unchanged_with_explicit_lang(self):
        self.assertEqual(transcribe.split_lines("你好。今天天气不错！", "Chinese"), ["你好。", "今天天气不错！"])


class SentencesTxt(unittest.TestCase):
    def test_english(self):
        self.assertEqual(transcribe.split_sentences_txt("Hi there. It is 3.5 now! Ok?", "English"),
                         "Hi there.\nIt is 3.5 now!\nOk?")

    def test_chinese(self):
        self.assertEqual(transcribe.split_sentences_txt("你好。再见！", "Chinese"), "你好。\n再见！")


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



class ParseCount(unittest.TestCase):
    def test_cases(self):
        cases = {
            "262": (262, False),
            "4,404": (4404, False),
            "20.2K": (20200, True),
            "1.2万": (12000, True),
            "3.4w": (34000, True),
            "10万+": (100000, True),
            "": (None, False),
            "abc": (None, False),
        }
        for text, expected in cases.items():
            self.assertEqual(xiaohongshu.parse_count(text), expected, text)

    def test_non_string(self):
        self.assertEqual(xiaohongshu.parse_count(None), (None, False))


class StatsMapping(unittest.TestCase):
    def test_douyin_play_count_zero_is_none(self):
        aweme = {"statistics": {"digg_count": 4548, "comment_count": 139, "collect_count": 5500,
                                "share_count": 1321, "play_count": 0, "recommend_count": 37, "admire_count": 0}}
        self.assertEqual(douyin.stats_from_aweme(aweme), {
            "views": None, "likes": 4548, "comments": 139, "favorites": 5500, "shares": 1321,
            "approximate": [], "extra": {"recommends": 37},
        })

    def test_douyin_without_statistics(self):
        self.assertIsNone(douyin.stats_from_aweme({}))

    def test_bilibili_api(self):
        stat = {"view": 12606, "danmaku": 2, "reply": 27, "favorite": 1354, "coin": 335, "share": 127, "like": 692}
        self.assertEqual(bilibili.stats_from_api(stat), {
            "views": 12606, "likes": 692, "comments": 27, "favorites": 1354, "shares": 127,
            "approximate": [], "extra": {"coins": 335, "danmaku": 2},
        })

    def test_bilibili_info_fallback(self):
        info = {"view_count": 100, "like_count": 5, "comment_count": 2}
        stats = bilibili.stats_from_info(info)
        self.assertEqual((stats["views"], stats["likes"], stats["comments"]), (100, 5, 2))
        self.assertIsNone(stats["favorites"])
        self.assertIsNone(stats["shares"])

    def test_xiaohongshu_html(self):
        html = ('<script>window.__INITIAL_STATE__={"note":{"interactInfo":{"collected":false,'
                '"collectedCount":"31K","sticky":false,"niceCount":"13","liked":false,'
                '"commentCount":"262","shareCount":"4,404","followed":false,"relation":"none",'
                '"likedCount":"20.2K"},"title":"x"}}</script>')
        self.assertEqual(xiaohongshu.stats_from_html(html), {
            "views": None, "likes": 20200, "comments": 262, "favorites": 31000, "shares": 4404,
            "approximate": ["likes", "favorites"],
            "extra": {"raw": {"likedCount": "20.2K", "collectedCount": "31K",
                              "commentCount": "262", "shareCount": "4,404"}},
        })

    def test_xiaohongshu_html_without_interact_info(self):
        self.assertIsNone(xiaohongshu.stats_from_html("<html></html>"))

    def test_youtube_info(self):
        info = {"view_count": 1000, "like_count": 50, "comment_count": 7, "channel_follower_count": 300}
        self.assertEqual(youtube.stats_from_info(info), {
            "views": 1000, "likes": 50, "comments": 7, "favorites": None, "shares": None,
            "approximate": [], "extra": {"channel_followers": 300},
        })


class AutoLanguage(unittest.TestCase):
    def test_auto_passes_through(self):
        self.assertEqual(fetch.pick_language(None, "auto"), "auto")
        self.assertEqual(fetch.pick_language("en", "auto"), "English")

    def test_orphan_word_merged(self):
        lines = transcribe.wrap_words("one two three four five six seven", 14)
        self.assertNotIn(" ", lines[-1][-1:])  # 不以空格结尾
        self.assertTrue(all(" " in l for l in lines), lines)

    def test_two_lines_with_orphan(self):
        # 只有两行且第二行是孤词：合并成一行
        self.assertEqual(transcribe.wrap_words("And that's pretty much all there is to say", 38),
                         ["And that's pretty much all there is to say"])


if __name__ == "__main__":
    unittest.main()
