"""B站下载器：yt-dlp 子进程。细节见 references/bilibili.md。"""
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from . import FetchError, make_stats

NAME = "bilibili"

STAT_API = "https://api.bilibili.com/x/web-interface/view?bvid="

BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def match(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com")


def extract_bv(url):
    found = BV_RE.search(url)
    return found.group(0) if found else None


def resolve(url):
    final = url
    if (urllib.parse.urlparse(url).hostname or "") == "b23.tv":
        # 短链的 BV 号只在跳转后的地址里
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                final = resp.geturl()
        except OSError as e:
            raise FetchError(f"b23.tv 短链跳转失败：{e}。检查网络或换成 bilibili.com/video/BV… 的完整链接。")
    bv = extract_bv(final)
    if bv is None:
        raise FetchError(f"没有从链接里找到 BV 号：{final}。目前只支持 bilibili.com/video/BV… 与 b23.tv 短链。")
    canonical = f"https://www.bilibili.com/video/{bv}/"
    # 分 P 视频只下链接指定的那一 P，规范链接保留 p 参数
    p = urllib.parse.parse_qs(urllib.parse.urlparse(final).query).get("p")
    if p:
        canonical += f"?p={p[0]}"
    return bv, canonical


def fetch(url, video_id, outdir, opts):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bv*[height<=1080]+ba/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        # 进度条会刷满输出，调用方只需要结果和报错
        "--no-progress",
        "--write-info-json",
        "--write-subs", "--sub-langs", "all,-danmaku", "--convert-subs", "srt",
        "-P", str(outdir),
        "-P", f"subtitle:{outdir / 'subtitles'}",
        "-P", f"infojson:{outdir / 'raw'}",
        "-o", "video.%(ext)s",
    ]
    if opts.cookies:
        cmd += ["--cookies", opts.cookies]
    if opts.cookies_from_browser:
        cmd += ["--cookies-from-browser", opts.cookies_from_browser]
    cmd.append(url)

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise FetchError(f"yt-dlp 退出码 {result.returncode}，输出见上方。读 references/bilibili.md 的已知失败表；网络问题可重跑一次。")
    if not (outdir / "video.mp4").exists():
        raise FetchError("yt-dlp 成功退出但没有生成 video.mp4。检查输出里的实际格式与文件名。")

    info_files = sorted((outdir / "raw").glob("*.info.json"))
    if not info_files:
        raise FetchError("没有找到 yt-dlp 的 info.json，无法读取标题与作者。")
    info = json.loads(info_files[0].read_text(encoding="utf-8"))

    subs = sorted((outdir / "subtitles").glob("*.srt")) if (outdir / "subtitles").is_dir() else []
    return {
        "title": info.get("title", ""),
        "author": info.get("uploader", ""),
        "duration": info.get("duration"),
        "description": info.get("description", ""),
        "platform_subtitles": [str(p.relative_to(outdir)) for p in subs],
        "stats": fetch_stats(video_id, info),
    }


def stats_from_api(stat):
    """公开接口 view 返回的 data.stat 转统一 stats。纯函数，不联网。"""
    return make_stats(
        views=stat.get("view"),
        likes=stat.get("like"),
        comments=stat.get("reply"),
        favorites=stat.get("favorite"),
        shares=stat.get("share"),
        extra={"coins": stat.get("coin"), "danmaku": stat.get("danmaku")},
    )


def stats_from_info(info):
    """接口不可用时的退路：只有 yt-dlp 给的三项，其余 None。"""
    return make_stats(
        views=info.get("view_count"),
        likes=info.get("like_count"),
        comments=info.get("comment_count"),
    )


def fetch_stats(bvid, info):
    """优先调公开接口（项目更全，含收藏、分享、投币）；失败退回 info.json，不抛异常。"""
    req = urllib.request.Request(STAT_API + urllib.parse.quote(bvid), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("code") != 0:
            raise ValueError(f"接口 code={body.get('code')}")
        return stats_from_api(body["data"]["stat"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"警告：B站统计接口取数失败（{e}），互动数据退回 yt-dlp 的 info.json，只有播放、点赞、评论。", file=sys.stderr)
        return stats_from_info(info)
