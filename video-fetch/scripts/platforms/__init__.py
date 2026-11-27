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
        可选再带 "language"（ISO 语言代码，如 en、zh，不知道就 None 或不带）。
        opts 带 cookies、cookies_from_browser 两个属性（目前只有 B站用）。

下载失败一律抛 FetchError，message 写清问题、原因、处理办法；fetch.py 统一以退出码 1 退出。
平台模块顶层不得 import playwright 这类重依赖，放进函数里，保证单元测试不装它们也能导入。
"""


class FetchError(Exception):
    pass
