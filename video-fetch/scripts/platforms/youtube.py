"""YouTube 下载器：yt-dlp 子进程，结构同 bilibili.py。"""
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

from . import FetchError, make_stats

NAME = "youtube"

ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
# 路径形式的链接：/shorts/<ID>、/live/<ID>
PATH_ID_RE = re.compile(r"^/(?:shorts|live)/([A-Za-z0-9_-]{11})(?:/|$)")


def match(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def resolve(url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    video_id = None
    if host == "youtu.be":
        found = re.match(r"^/([A-Za-z0-9_-]{11})(?:/|$)", parsed.path)
        video_id = found.group(1) if found else None
    elif parsed.path == "/watch":
        v = urllib.parse.parse_qs(parsed.query).get("v")
        if v and ID_RE.fullmatch(v[0]):
            video_id = v[0]
    else:
        found = PATH_ID_RE.match(parsed.path)
        video_id = found.group(1) if found else None
    if video_id is None:
        raise FetchError(f"没有从链接里找到 11 位视频 ID：{url}。目前只支持 watch?v=、/shorts/、/live/ 和 youtu.be/ 形式的链接。")
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


def fetch(url, video_id, outdir, opts):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        # 优先 h264（avc1），QuickTime 能直接播；没有再退到任意编码
        "-f", "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        # 进度条会刷满输出，调用方只需要结果和报错
        "--no-progress",
        "--write-info-json",
        # 末尾两条排除 YouTube 的机器翻译轨（zh-Hans-en、en-de 这类：语言码后再跟一个小写语言码）。
        # 它们对转写没用，且下载时稳定返回 429，会让整个 yt-dlp 调用失败。
        # 正则里不能写 {2,3}：--sub-langs 按逗号拆分
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "zh.*,en.*,.*-orig,-live_chat,-zh-.*-[a-z][a-z][a-z]?,-en-[a-z][a-z][a-z]?",
        "--convert-subs", "srt",
        "-P", str(outdir),
        "-P", f"subtitle:{outdir / 'subtitles'}",
        "-P", f"infojson:{outdir / 'raw'}",
        "-o", "video.%(ext)s",
    ]
    # 新版 yt-dlp 下 YouTube 需要 JS 运行时，默认只认 deno；缺了会少格式和字幕
    if shutil.which("node"):
        cmd += ["--js-runtimes", "node"]
    elif not shutil.which("deno"):
        print("警告：没有找到 node 或 deno，YouTube 可能缺少部分格式和字幕。", file=sys.stderr)
    if opts.cookies:
        cmd += ["--cookies", opts.cookies]
    if opts.cookies_from_browser:
        cmd += ["--cookies-from-browser", opts.cookies_from_browser]
    cmd.append(url)

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise FetchError(f"yt-dlp 退出码 {result.returncode}，输出见上方。网络问题可重跑一次；提示需要登录或 bot 校验时加 --cookies-from-browser。")
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
        # YouTube 元数据常常没有语言（英文视频也是），这时让 ASR 自动识别，避免把英文当中文转写
        "language": info.get("language") or "auto",
        "stats": stats_from_info(info),
    }


def stats_from_info(info):
    """yt-dlp info.json 转统一 stats。YouTube 不公开收藏与分享数，写 None。"""
    return make_stats(
        views=info.get("view_count"),
        likes=info.get("like_count"),
        comments=info.get("comment_count"),
        extra={"channel_followers": info.get("channel_follower_count")},
    )
