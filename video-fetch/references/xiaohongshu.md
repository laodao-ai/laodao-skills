# 小红书

实测日期：2026-11-27，yt-dlp 2026.11.23。

## 下载

- 用 yt-dlp 自带的小红书提取器，不用登录。实测一条竖屏视频拿到 720×1280、h264 + aac。
- 链接必须带 `xsec_token`。不带时 yt-dlp 报 `No video formats found`。App 或网页「分享 → 复制链接」得到的链接都带它，脚本在规范链接里保留 `xsec_token` 和 `xsec_source`。
- 支持 `xiaohongshu.com/explore/<ID>` 和 `/discovery/item/<ID>`，笔记 ID 是 24 位十六进制。
- `xhslink.com`、`xhslink.cn` 短链还没测过，目前不支持。要加时先实测短链跳转后的地址是否带 `xsec_token`。

## 元数据与字幕

- yt-dlp 给出标题、时长和笔记正文（`description`），作者只给用户 ID（`uploader_id`），不给昵称。
- 实测的笔记没有平台字幕。脚本仍会请求字幕，有就存到 `subtitles/`。

## 为什么不用无头浏览器

参考仓 video-batch-download 用 Playwright 读页面的 `window.__INITIAL_STATE__`。实测无头 Chrome 打开笔记会被跳到登录页；按参考仓的做法从 `redirectPath` 取回原地址再打开，仍跳回登录页。

备用路线：用手机 UA 直接请求笔记页（`curl -L -A <iPhone UA> <链接>`），会跳到 `/discovery/item/<ID>`，服务端渲染的 HTML 里有 `__INITIAL_STATE__`，其中 `masterUrl` 就是视频地址。yt-dlp 失效时可以改走这条路。

## 已知失败

| 报错 | 可能原因 | 处理 |
|---|---|---|
| 链接里没有 xsec_token | 用户手动去掉了参数，或从别处拷来的裸链接 | 让用户重新「分享 → 复制链接」 |
| yt-dlp 报 `No video formats found` | 图文笔记；或 `xsec_token` 已失效 | 图文不支持；token 失效就重新复制分享链接 |
