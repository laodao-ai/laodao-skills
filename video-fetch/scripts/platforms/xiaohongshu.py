"""小红书下载器：yt-dlp 子进程。细节见 references/xiaohongshu.md。"""
import json
import re
import subprocess
import sys
import urllib.parse

from . import FetchError

NAME = "xiaohongshu"

# 笔记 ID 是 24 位十六进制；/explore/ 与 /discovery/item/ 是同一篇笔记的两种地址
NOTE_RE = re.compile(r"/(?:explore|discovery/item)/([0-9a-f]{24})")


def match(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com")


def resolve(url):
    parsed = urllib.parse.urlparse(url)
    found = NOTE_RE.search(parsed.path)
    if found is None:
        raise FetchError(f"没有从链接里找到笔记 ID：{url}。目前只支持 xiaohongshu.com/explore/<ID> 与 /discovery/item/<ID>。")
    note_id = found.group(1)
    query = urllib.parse.parse_qs(parsed.query)
    # 不带 xsec_token 时页面不给视频数据，yt-dlp 报 No video formats found
    token = query.get("xsec_token", [None])[0]
    if not token:
        raise FetchError("链接里没有 xsec_token，拿不到视频。请用小红书 App 或网页「分享 → 复制链接」得到的完整链接。")
    keep = {"xsec_token": token, "xsec_source": query.get("xsec_source", ["app_share"])[0]}
    return note_id, f"https://www.xiaohongshu.com/explore/{note_id}?{urllib.parse.urlencode(keep)}"


def fetch(url, video_id, outdir, opts):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        # 进度条会刷满输出，调用方只需要结果和报错
        "--no-progress",
        "--write-info-json",
        "--write-subs", "--sub-langs", "all", "--convert-subs", "srt",
        "-P", str(outdir),
        "-P", f"subtitle:{outdir / 'subtitles'}",
        "-P", f"infojson:{outdir / 'raw'}",
        "-o", "video.%(ext)s",
        "--merge-output-format", "mp4",
    ]
    if opts.cookies:
        cmd += ["--cookies", opts.cookies]
    if opts.cookies_from_browser:
        cmd += ["--cookies-from-browser", opts.cookies_from_browser]
    cmd.append(url)

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise FetchError(
            f"yt-dlp 退出码 {result.returncode}，输出见上方。"
            "报 No video formats found 时，可能是图文笔记（不支持）或 xsec_token 已失效（重新复制分享链接）；"
            "其他情况读 references/xiaohongshu.md。"
        )
    if not (outdir / "video.mp4").exists():
        raise FetchError("yt-dlp 成功退出但没有生成 video.mp4。检查输出里的实际格式与文件名。")

    info_files = sorted((outdir / "raw").glob("*.info.json"))
    if not info_files:
        raise FetchError("没有找到 yt-dlp 的 info.json，无法读取标题。")
    info = json.loads(info_files[0].read_text(encoding="utf-8"))

    subs = sorted((outdir / "subtitles").glob("*.srt")) if (outdir / "subtitles").is_dir() else []
    return {
        "title": info.get("title", ""),
        # yt-dlp 目前只给作者的用户 ID，不给昵称
        "author": info.get("uploader") or info.get("uploader_id") or "",
        "duration": info.get("duration"),
        "description": info.get("description", ""),
        "platform_subtitles": [str(p.relative_to(outdir)) for p in subs],
    }
