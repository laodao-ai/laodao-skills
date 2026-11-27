---
name: video-fetch
description: 当用户给出 B站或抖音视频链接（含抖音 App 复制的整段分享文本），要求下载视频、分离音频、获取字幕、转写口播稿或逐字稿时使用。
---

# 下载视频并转写口播稿

一个链接产出视频、音频、字幕和口播稿。各平台只有下载这一步不同，每个平台一个下载器；抽音频和转写共用。

## 依赖

- `uv`、`ffmpeg`、`ffprobe`；转写要 Apple Silicon（mlx-audio）。
- 脚本用 PEP 723 头声明 Python 依赖，`uv run` 首次运行自动安装。
- 抖音要无头浏览器：优先用本机 Google Chrome；没有 Chrome 时按脚本报错提示装 Playwright 的 Chromium。
- 转写模型 `Qwen3-ASR-1.7B-8bit` 与 `Qwen3-ForcedAligner-0.6B-8bit`（mlx-community）。脚本依次找 `$VIDEO_FETCH_MODELS_DIR`、`~/.omlx/models/mlx-community`、`/Users/Shared/.omlx/models/mlx-community`；都没有就从 Hugging Face 下载，约 3 GB。

## 执行

1. 输出目录用用户指定的；未指定时脚本在当前目录建 `<平台>-<视频ID>/`。
2. 运行（`<skill-dir>` 换成本 `SKILL.md` 所在目录的绝对路径）：

   ```bash
   uv run <skill-dir>/scripts/fetch.py '<链接或整段分享文本>' [--output <目录>] \
     [--cookies <cookies.txt> | --cookies-from-browser <浏览器>] [--no-asr]
   ```

   多个链接一个一个跑，不要并行，并行容易触发平台风控。
3. 看退出码和输出的最后几行：`0` 全部完成；`2` 视频已下载但转写失败，按输出里的原因处理；`1` 失败（链接不支持、输出目录已存在、下载出错），按报错处理，不能报成功。
4. 读 `meta.json`，抽看 `transcript.srt` 开头和结尾各几条。向用户报告：标题、作者、时长、各文件路径、平台字幕有没有拿到、字幕条数（`meta.json` 的 `transcript.lines`）。说明稿子是语音识别结果，人名和术语可能有错。

## 输出

| 文件 | 内容 |
|---|---|
| `video.mp4` | 视频。B站限高 1080，不登录拿不到 1080P 60 帧 |
| `audio.m4a` | 原音轨，不重新编码 |
| `transcript.srt` | 本机转写的字幕，按标点断条，长句在逗号处再拆；时间由强制对齐给出 |
| `transcript.txt` | 纯文本口播稿，按句号、问号、叹号断行，所以行数少于字幕条数 |
| `subtitles/` | 平台自带字幕，拿到时才有 |
| `meta.json` | 标题、作者、时长、简介、各步状态 |
| `raw/` | 平台原始数据（yt-dlp info.json、抖音接口 JSON） |

平台字幕和本机转写并存：前者是平台原文，后者格式统一、时间轴逐句。

## 平台

| 平台 | 支持的链接 | 下载方式 | 平台字幕 | 细节 |
|---|---|---|---|---|
| B站 | `bilibili.com/video/BV…`、`b23.tv/…` | yt-dlp | 要登录 cookie | `references/bilibili.md` |
| 抖音 | `v.douyin.com/…`、`douyin.com/video/…`、分享文本 | 无头浏览器截获作品接口 | 通常没有 | `references/douyin.md` |

下载出错时先读对应平台的细节文件，里面记了已知失败和处理办法。

## 加一个平台

1. 先读 `references/video-batch-download.md`，里面记了小红书、快手、微博的数据来源和坑。
2. 新建 `scripts/platforms/<平台>.py`，实现 `match(url)`、`resolve(url)`、`fetch(...)`，接口以 `scripts/platforms/__init__.py` 的说明为准。
3. 在 `scripts/fetch.py` 的 `PLATFORMS` 列表里登记。
4. 新建 `references/<平台>.md`，写清下载方式、字幕情况、已知失败。
5. 在上面的平台表加一行，在 `tests/` 补链接识别的用例。

## 常见问题

| 现象 | 处理 |
|---|---|
| B站提示 `Subtitles are only available when logged in` | 视频仍会下载和转写。要平台字幕，请用户提供 cookies.txt 或登录 B站的浏览器名，再用 `--cookies` 或 `--cookies-from-browser` 重跑 |
| `--cookies-from-browser` 报找不到 cookie 库或不支持该浏览器 | 换浏览器，或让用户用浏览器插件导出 cookies.txt。yt-dlp 不支持 Arc；Safari 需要终端有完全磁盘访问权限 |
| 抖音链接是图文作品 | 不支持，脚本会报错退出 |
| 抖音报没截到作品接口 | 读 `references/douyin.md`。不要改用 yt-dlp 下抖音，它会被 403 拒绝 |
