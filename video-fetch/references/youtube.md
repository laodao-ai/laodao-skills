# YouTube

实测日期：2026-11-27，yt-dlp 2026.11.23。

## 下载

- 用 yt-dlp。支持 `youtube.com/watch?v=<ID>`、`/shorts/<ID>`、`/live/<ID>`、`youtu.be/<ID>`，ID 是 11 位。加 `--no-playlist`，链接带播放列表参数时只下这一条。
- 格式优先 1080P 以内的 h264 + m4a，合成 mp4，QuickTime 能直接播；没有 h264 时退回其他编码。
- 新版 yt-dlp 下 YouTube 需要 JS 运行时，默认只认 deno。缺了会报 `No supported JavaScript runtime could be found`，并可能少格式和字幕。脚本在本机有 Node 时加 `--js-runtimes node`；Node 和 deno 都没有时打印警告继续跑。
- 一次只跑一个 yt-dlp 进程。YouTube 对并行请求会触发 bot 校验。

## 字幕

- 请求的字幕：作者上传的中文、英文字幕，以及原语言的自动字幕（`*-orig`）。存到 `subtitles/`。
- 排除了机器翻译字幕轨（如 `zh-Hans-en`、`en-de`）。这些轨道下载时稳定返回 HTTP 429，会让整个 yt-dlp 调用失败。
- 很多视频没有任何字幕，包括没有自动字幕。实测的中文视频 `3DlXq9nsQOE` 就是这样，只能本机转写。

## 转写语言

- YouTube 的 info.json 里 `language` 经常为空，英文视频也一样。
- 为空时脚本传 `auto`，Qwen3-ASR 自己识别语言，对齐和断句用识别结果，`meta.json` 的 `language` 记实际语言。实测英文、中文各一条都识别正确。
- 识别错了就用 `--lang en`、`--lang zh` 等指定后重跑。

## 已知失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `No supported JavaScript runtime could be found` | 本机没有 Node 和 deno | 装 Node（`brew install node`） |
| 字幕请求报 HTTP 429 | 请求了机器翻译字幕轨，或请求过于频繁 | 检查 `--sub-langs` 是否放进了翻译轨；等一会儿重跑 |
| `Sign in to confirm you're not a bot` | 被 YouTube 风控 | 隔一段时间重跑；仍不行就带 `--cookies-from-browser` |

## 互动数据

取自 yt-dlp info.json：播放 `view_count`、点赞 `like_count`、评论 `comment_count`，频道订阅数放 `extra.channel_followers`。YouTube 不公开收藏和分享，写 `null`。评论数和订阅数较大时是 yt-dlp 从页面显示文字换算的约数（如 10000000 来自「10M」），脚本无法区分，不进 `approximate`，引用时注意。
