"""平台下载器接口。每个平台一个模块，由 fetch.py 的 PLATFORMS 列表登记。

模块必须提供：

    NAME: str
        平台名，用于默认输出目录 `<NAME>-<视频ID>/` 和 meta.json 的 platform 字段。

    match(url: str) -> bool
        只看链接本身（域名、路径），不联网。

    resolve(url: str) -> tuple[str, str]
        返回 (视频ID, 规范链接)。短链在这里跟随跳转；不支持的作品类型（如抖音图文）
        抛 FetchError。

    fetch(url: str, video_id: str, outdir: Path, opts) -> dict
        下载到 outdir。必须写出：
          outdir/video.mp4        含视频流与音频流
          outdir/raw/             平台原始数据
          outdir/subtitles/       平台字幕（有才建）
        返回 {"title", "author", "duration", "description", "platform_subtitles"}，
        duration 为秒，platform_subtitles 是相对 outdir 的路径列表。
        可选再带 "published"（发布日期，字符串 YYYY-MM-DD，按东八区换算，拿不到就 None 或不带；
        换算用本模块的 date_from_timestamp / date_from_ytdlp_info，不要各平台自己写）。
        可选再带 "language"（ISO 语言代码，如 en、zh，不知道就 None 或不带）。
        可选再带 "stats"（互动数据），结构由 make_stats() 生成：
          {"views": int|None, "likes": int|None, "comments": int|None,
           "favorites": int|None, "shares": int|None,
           "approximate": [字段名...],   # 数值由「20.2K」「1.2万」这类约数换算而来的字段
           "extra": {...}}               # 平台独有数据与原始显示字符串
        拿不到的项一律 None，不能写 0（0 会被当成真实的零）。
        取统计数据失败不得抛 FetchError：在平台内部捕获、往 stderr 打一行警告、
        返回 "stats": None 或不带该键，不影响下载与转写。
        opts 带 cookies、cookies_from_browser 两个属性（目前只有 B站用）。

下载失败一律抛 FetchError，message 写清问题、原因、处理办法；fetch.py 统一以退出码 1 退出。
平台模块顶层不得 import playwright 这类重依赖，放进函数里，保证单元测试不装它们也能导入。
"""


from datetime import datetime, timedelta, timezone

# 发布日期统一按东八区换算：作者与观众都在国内，同一个时刻在不同平台不会因时区差一天
CST = timezone(timedelta(hours=8))


class FetchError(Exception):
    pass


def date_from_timestamp(ts):
    """Unix 秒转东八区日期 YYYY-MM-DD。None、非数字返回 None。纯函数，不联网。"""
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return None
    return datetime.fromtimestamp(ts, CST).strftime("%Y-%m-%d")


def date_from_ytdlp_info(info):
    """yt-dlp info.json 取发布日期：先用 upload_date（"20260807"），没有再用 timestamp 换算。

    upload_date 是 yt-dlp 已按平台口径算好的日期，直接改格式，不再换时区。
    """
    upload_date = info.get("upload_date")
    if isinstance(upload_date, str) and len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    return date_from_timestamp(info.get("timestamp"))


def make_stats(views=None, likes=None, comments=None, favorites=None, shares=None, approximate=(), extra=None):
    """生成统一结构的 stats 字典，字段说明见上方 fetch 的接口说明。"""
    return {
        "views": views,
        "likes": likes,
        "comments": comments,
        "favorites": favorites,
        "shares": shares,
        "approximate": list(approximate),
        "extra": dict(extra) if extra else {},
    }
