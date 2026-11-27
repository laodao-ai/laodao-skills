# 抖音

实测日期：2026-11-27。

## 下载方式

1. 从输入里找出链接。抖音 App 复制出来的是一段文字加短链，脚本用正则取出第一个 `https://` 链接。
2. 解析作品 ID：用手机 UA 请求短链，跟随跳转，从最终地址取 `/video/<ID>`。地址是 `/note/<ID>` 时是图文作品，不支持。
3. 用无头浏览器打开 `https://www.douyin.com/video/<ID>`，等页面自己请求 `aweme/v1/web/aweme/detail` 接口，截下返回的 JSON（存 `raw/detail.json`）。
4. 从 `aweme_detail.video.bit_rate` 里取码率最高的 `play_addr.url_list[0]`，带 `Referer: https://www.douyin.com/` 和桌面 UA 直接下载。这个地址是无水印的，几小时后失效，所以拿到就下。

## 为什么不用别的办法

| 办法 | 结果 |
|---|---|
| yt-dlp | 请求作品接口被 403，报 `Fresh cookies (not necessarily logged in) are needed`；带上浏览器里拿到的访客 cookie 也一样，因为接口还要签名参数 |
| `iesdouyin.com/share/video/<ID>` 分享页 | 服务端渲染里只有页面配置，没有视频数据，视频数据由前端再请求 |
| 无头浏览器截接口 | 可用。签名由抖音自己的页面脚本生成，不用自己实现 |

## 字幕

- 抖音作品接口里 `is_subtitled` 为 0 时没有字幕。`caption` 和 `desc` 是作品简介，不是字幕。
- 所以抖音的稿子全靠本机转写。

## 已知失败

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 没截到作品接口 | 页面改版、被风控、网络慢 | 先重跑一次；仍失败就用有界面的浏览器打开同一链接看是否要验证码，再看接口路径是否改名 |
| 下载的视频没有音轨 | 取到了只含视频的分轨地址 | 检查是否误用了页面里 `media-video-avc1` 这类分轨请求；应只用接口 JSON 的 `bit_rate` / `play_addr` |
| Playwright 报找不到浏览器 | 本机没有 Chrome，也没装 Playwright 的 Chromium | 按报错提示运行安装命令 |
