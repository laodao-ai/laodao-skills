# B站

实测日期：2026-11-27，yt-dlp 2026.11.23。

## 下载

- 用 yt-dlp。不登录也能下到 1080P；4K 和 1080P 60 帧要大会员 cookie。脚本限定最高 1080P，避免大会员 cookie 下默认拉 4K 大文件。
- 加 `--no-playlist`：分 P 视频只下链接指定的那一 P（`?p=N`），不下整个合集。
- `b23.tv` 短链由 yt-dlp 跟随跳转，不用手动解析。

## 平台字幕

- B站字幕分 UP 主上传的 CC 字幕和 AI 字幕（语言代码形如 `ai-zh`）。两种都要登录才能拿；不登录时 yt-dlp 只列出 `danmaku`（弹幕，不是字幕），脚本会排除它。
- 不登录时无法判断视频到底有没有字幕。
- cookie 来源：
  - `--cookies-from-browser`：yt-dlp 支持 brave、chrome、chromium、edge、firefox、opera、safari、vivaldi、whale，不支持 Arc。Chromium 系浏览器读取时会弹钥匙串授权。Safari 的 cookie 文件受系统保护，终端要有完全磁盘访问权限。浏览器的 cookie 库不存在时报 `could not find ... cookies database`，说明这个浏览器没用过或没登录过。
  - `--cookies <cookies.txt>`：用户用浏览器插件导出的 Netscape 格式文件，最稳。

## 已知失败

| 报错 | 原因 | 处理 |
|---|---|---|
| `Subtitles are only available when logged in` | 没带 cookie | 正常继续，转写照做；要平台字幕就带 cookie 重跑 |
| `Format(s) 4K ... are missing` | 非大会员 | 忽略，脚本本来就只取 1080P |

## 互动数据

调公开接口 `https://api.bilibili.com/x/web-interface/view?bvid=<BV号>`，不用登录，返回 `data.stat`：播放、点赞、评论、收藏、分享都有，投币和弹幕数放 `extra`。接口失败时退回 yt-dlp info.json 的播放、点赞、评论三项。
