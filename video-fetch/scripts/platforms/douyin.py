"""抖音下载器：无头浏览器截获作品接口，再直链下载。细节见 references/douyin.md。"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import FetchError, date_from_timestamp, make_stats

NAME = "douyin"

# 与 playwright 版本一起实测过；浏览器安装提示用同一个版本
PLAYWRIGHT_VERSION = "1.65.2"
DESKTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
DETAIL_API = "aweme/v1/web/aweme/detail"
CAPTURE_TIMEOUT = 20  # 秒；截到接口就提前结束


def match(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return host == "douyin.com" or host.endswith(".douyin.com") or host.endswith("iesdouyin.com")


def id_from_url(url):
    """返回 ("video"|"note", ID)，找不到返回 None。"""
    found = re.search(r"/(video|note)/(\d+)", url)
    return (found.group(1), found.group(2)) if found else None


def resolve(url):
    parsed = id_from_url(url)
    if parsed is None:
        # 短链：手机 UA 请求，跟随跳转，ID 在最终地址里
        req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = id_from_url(resp.geturl())
        except OSError as e:
            raise FetchError(f"抖音短链跳转失败：{e}。检查网络，或直接给 douyin.com/video/<ID> 链接。")
    if parsed is None:
        raise FetchError("没有从链接或其跳转地址里找到作品 ID。确认链接是抖音视频作品。")
    kind, video_id = parsed
    if kind == "note":
        raise FetchError("这是图文作品，不支持。目前只支持视频作品。")
    return video_id, f"https://www.douyin.com/video/{video_id}"


def capture_detail(canonical):
    """用无头浏览器打开作品页，返回页面自己请求到的作品接口 JSON。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise FetchError("没有安装 playwright。请通过 `uv run scripts/fetch.py` 运行，让 uv 按脚本头装依赖。")

    captured = {}

    def on_response(resp):
        if DETAIL_API not in resp.url or "data" in captured:
            return
        try:
            data = resp.json()
        except Exception:
            return
        # 接口偶尔先返回空的 aweme_detail，只收有内容的；空的留着，超时后用来说明原因
        if data.get("aweme_detail"):
            captured["data"] = data
        else:
            captured["empty"] = data

    with sync_playwright() as p:
        browser = None
        errors = []
        # 优先本机 Chrome，省掉下载 Chromium
        for label, kwargs in (("chrome", {"channel": "chrome"}), ("chromium", {})):
            try:
                browser = p.chromium.launch(headless=True, **kwargs)
                break
            except Exception as e:
                errors.append(f"{label}: {str(e).splitlines()[0]}")
        if browser is None:
            raise FetchError(
                "无法启动浏览器（" + "；".join(errors) + "）。\n"
                f"安装 Playwright 的 Chromium：uv run --with playwright=={PLAYWRIGHT_VERSION} playwright install chromium"
            )
        try:
            ctx = browser.new_context(user_agent=DESKTOP_UA, locale="zh-CN")
            page = ctx.new_page()
            page.on("response", on_response)
            page.goto(canonical, wait_until="domcontentloaded", timeout=60000)
            deadline = time.monotonic() + CAPTURE_TIMEOUT
            while "data" not in captured and time.monotonic() < deadline:
                page.wait_for_timeout(500)
        finally:
            browser.close()

    if "data" not in captured and "empty" in captured:
        empty = captured["empty"]
        raise FetchError(
            f"作品接口返回了空内容（status_code={empty.get('status_code')}，"
            f"filter_detail={json.dumps(empty.get('filter_detail'), ensure_ascii=False)}）。"
            "作品可能已删除、设为私密或在审核中；在浏览器里打开链接确认。"
        )
    if "data" not in captured:
        raise FetchError(f"{CAPTURE_TIMEOUT} 秒内没截到作品接口。先重跑一次；仍失败读 references/douyin.md 的已知失败表。")
    return captured["data"]


# 图文作品的 aweme_type，取自 github.com/ljb1020/video-batch-download（MIT）的抖音适配器；
# 短链跳到 /video/ 也可能是图文，所以还要看接口里的 images
IMAGE_AWEME_TYPES = (68, 150)


def check_playable(aweme):
    status = aweme.get("status") or {}
    if status.get("is_delete") or status.get("is_prohibited"):
        raise FetchError("作品已删除或被下架。")
    if status.get("private_status"):
        raise FetchError("作品是私密的，不登录拿不到。")
    if aweme.get("images") or aweme.get("aweme_type") in IMAGE_AWEME_TYPES:
        raise FetchError("这是图文作品，不支持。目前只支持视频作品。")


def best_play_url(detail):
    video = detail["aweme_detail"].get("video") or {}
    rates = video.get("bit_rate") or []
    if not rates:
        raise FetchError("作品接口里没有 bit_rate 列表，无法取下载地址。抖音接口结构可能改了，读 references/douyin.md。")
    best = max(rates, key=lambda r: r.get("bit_rate", 0))
    urls = (best.get("play_addr") or {}).get("url_list") or []
    if not urls:
        raise FetchError("最高码率项里没有 play_addr.url_list。抖音接口结构可能改了，读 references/douyin.md。")
    url = urls[0]
    return "https:" + url if url.startswith("//") else url


def download(play_url, dest):
    req = urllib.request.Request(play_url, headers={"User-Agent": DESKTOP_UA, "Referer": "https://www.douyin.com/"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            while True:
                block = resp.read(1 << 20)
                if not block:
                    break
                f.write(block)
    except OSError as e:
        raise FetchError(f"下载视频失败：{e}。地址几小时后失效，重跑会重新取地址。")


def check_streams(path):
    import subprocess
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    kinds = set(out.stdout.split())
    if out.returncode != 0 or not {"video", "audio"} <= kinds:
        raise FetchError("下载的 video.mp4 缺视频流或音频流。读 references/douyin.md 的「下载的视频没有音轨」一行。")


def fetch(url, video_id, outdir, opts):
    raw = outdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    detail = capture_detail(url)
    (raw / "detail.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")

    aweme = detail["aweme_detail"]
    check_playable(aweme)
    download(best_play_url(detail), outdir / "video.mp4")
    check_streams(outdir / "video.mp4")

    duration_ms = (aweme.get("video") or {}).get("duration")
    return {
        # item_title 是作者填的标题；desc 是标题加简介和话题，没有标题时才用它
        "title": aweme.get("item_title") or aweme.get("desc", ""),
        "author": (aweme.get("author") or {}).get("nickname", ""),
        "duration": duration_ms / 1000 if duration_ms else None,
        # create_time 是 Unix 秒
        "published": date_from_timestamp(aweme.get("create_time")),
        "description": aweme.get("desc", ""),
        "platform_subtitles": [],
        "stats": stats_from_aweme(aweme),
    }


def stats_from_aweme(aweme):
    """aweme_detail.statistics 转统一 stats。纯函数，不联网。"""
    s = aweme.get("statistics")
    if not s:
        return None
    # play_count 恒为 0 表示作者未公开播放量，不是真的 0 次播放，所以 views 写 None
    return make_stats(
        views=None,
        likes=s.get("digg_count"),
        comments=s.get("comment_count"),
        favorites=s.get("collect_count"),
        shares=s.get("share_count"),
        extra={"recommends": s.get("recommend_count")},
    )
