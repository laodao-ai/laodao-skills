"""小红书下载器：yt-dlp 子进程。细节见 references/xiaohongshu.md。"""
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from . import FetchError, date_from_timestamp, make_stats

NAME = "xiaohongshu"

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
# interactInfo 的值里没有嵌套花括号，非贪婪取到第一个 } 即可
INTERACT_RE = re.compile(r'"interactInfo":(\{[^{}]*\})')
# 数字 + 可选单位 + 可选 +；逗号已先去掉
COUNT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([KkMmWw万亿]?)(\+?)$")
UNIT_FACTORS = {"": 1, "k": 1_000, "m": 1_000_000, "w": 10_000, "万": 10_000, "亿": 100_000_000}

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


def date_from_note_id(note_id):
    """笔记 ID 前 8 位十六进制是创建时间的 Unix 秒（类似 MongoDB ObjectId）。

    依据：实测 6a672b10… -> 1785146128，与笔记页数据里的发布时间完全相同。
    yt-dlp 不给发布时间，所以用这个。ID 格式不对返回 None。纯函数，不联网。
    """
    if not isinstance(note_id, str) or not re.fullmatch(r"[0-9a-f]{24}", note_id):
        return None
    return date_from_timestamp(int(note_id[:8], 16))


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
    # yt-dlp 不给互动数据和作者昵称（只给用户 ID），都从手机版笔记页取
    html = fetch_page(url)
    user_id = info.get("uploader_id") or ""
    nickname = nickname_from_html(html, user_id) if html else None
    return {
        "title": info.get("title", ""),
        "author": info.get("uploader") or nickname or user_id,
        "duration": info.get("duration"),
        "published": date_from_note_id(video_id),
        "description": info.get("description", ""),
        "platform_subtitles": [str(p.relative_to(outdir)) for p in subs],
        "stats": stats_from_page(html),
    }


def parse_count(text):
    """把页面上的计数字符串转成 (整数, 是否约数)。

    "262"->(262, False)；"4,404"->(4404, False)；"20.2K"->(20200, True)；
    "1.2万"->(12000, True)；"10万+"->(100000, True)；空或无法解析->(None, False)。
    """
    if not isinstance(text, str):
        return None, False
    found = COUNT_RE.match(text.strip().replace(",", ""))
    if found is None:
        return None, False
    number, unit, plus = found.groups()
    value = int(round(float(number) * UNIT_FACTORS[unit.lower()]))
    return value, bool(unit or plus)


def stats_from_html(html):
    """从笔记页 HTML 的 interactInfo 取互动数据。找不到或解析失败返回 None。纯函数，不联网。"""
    found = INTERACT_RE.search(html)
    if found is None:
        return None
    try:
        info = json.loads(found.group(1))
    except ValueError:
        return None
    raw = {key: info.get(key) for key in ("likedCount", "collectedCount", "commentCount", "shareCount")}
    likes, likes_approx = parse_count(raw["likedCount"])
    favorites, favorites_approx = parse_count(raw["collectedCount"])
    comments, comments_approx = parse_count(raw["commentCount"])
    shares, shares_approx = parse_count(raw["shareCount"])
    approximate = [
        name for name, flag in (
            ("likes", likes_approx), ("favorites", favorites_approx),
            ("comments", comments_approx), ("shares", shares_approx),
        ) if flag
    ]
    # 小红书不公开播放量，views 写 None
    return make_stats(
        views=None, likes=likes, comments=comments, favorites=favorites, shares=shares,
        approximate=approximate, extra={"raw": raw},
    )


def nickname_from_html(html, user_id):
    """按用户 ID 找作者昵称。页面里还有评论者的 user 块，所以必须用 ID 定位。纯函数，不联网。"""
    if not user_id:
        return None
    found = re.search(r'"userId":"' + re.escape(user_id) + r'","nickName":"([^"]+)"', html)
    return found.group(1) if found else None


def fetch_page(url):
    """用手机 UA 请求笔记页（服务端渲染里有互动数据和作者昵称）。失败只警告，返回 None。"""
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except OSError as e:
        print(f"警告：小红书笔记页请求失败（{e}），作者只记用户 ID，meta.json 的 stats 写 null。", file=sys.stderr)
        return None


def stats_from_page(html):
    if html is None:
        return None
    stats = stats_from_html(html)
    if stats is None:
        print("警告：小红书页面里没找到可解析的 interactInfo，meta.json 的 stats 写 null。", file=sys.stderr)
    return stats
