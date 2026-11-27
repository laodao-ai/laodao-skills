# 参考：video-batch-download

来源：<https://github.com/ljb1020/video-batch-download>，MIT 许可，Node 实现。
查阅日期 2026-11-27，对应提交 `be5e41cf7e95`。移植它的代码或规则时，在注释里注明出处。

它支持抖音、B站、快手、小红书、微博，下载全靠 Playwright 截获页面请求，转写用 faster-whisper。
本文只记对本 skill 有用的部分。行号对应上面的提交。

## 已采用

- 抖音：按 `aweme_type` 为 68、150 或 `images` 非空识别图文作品；接口 `status` 里 `is_delete`、`private_status` 等字段判断不可下载（`scripts/platforms/douyin.js`）。
- 抖音截接口的做法和本 skill 一致，可互相印证。

## 加平台时参考

### 小红书（`scripts/platforms/xiaohongshu.js`）

> 本 skill 已支持小红书，但没有用下面的浏览器路线：实测无头 Chrome 被跳到登录页，取回 `redirectPath` 再开仍然如此。现用 yt-dlp，见 `references/xiaohongshu.md`。下面的内容留作 yt-dlp 失效时的参考。

- 链接：`xiaohongshu.com/explore/<id>`、`/discovery/item/<id>`、`/note/<id>`，短链 `xhslink.cn/…`、`xhslink.com/…`。
- 数据来源：页面的 `window.__INITIAL_STATE__` 里的笔记数据，按笔记 ID 取 `noteDetailMap[noteId]`（约 346–366 行）。
- 视频流在 `note.video.media.stream` 下按编码分组：`h264`、`h265`、`av1`、`h266`（约 444–460 行）。另有 `originVideoKey`，可拼成 `https://sns-video-bd.xhscdn.com/<key>`（约 466 行）。
- 坑：
  - 短链可能跳到登录页，目标地址在 `redirectPath` 参数里，取出来再打开一次（约 124–126、375–378 行）。
  - 必须核对笔记 ID 与目标一致，不能拿推荐流里的其他笔记顶替。
  - 只收能直接下载的 MP4，排除 HLS（`.m3u8`、`.ts`、`mpegurl`）。
  - 时长字段有的是秒有的是毫秒，按数值大小区分（约 431 行）。
  - 下载带 `Referer: https://www.xiaohongshu.com/`。
  - 图文笔记不支持。

### 快手（`scripts/platforms/kuaishou.js`）

- 链接：`kuaishou.com/short-video/…`、`v.kuaishou.com/…`、`kuaishou.com/f/…`、`m.kuaishou.com/(v|short-video)/…`、`gifshow.com/…`。
- 数据来源两处：截获 `/graphql` 响应里的 `photo`（约 60–65 行）；或读页面 `window.__APOLLO_STATE__.defaultClient` 中 `VisionVideoDetailPhoto:<photoId>`（约 218–234 行）。
- 地址候选：`photoUrl`、`photoH265Url`、`videoResource` 里各清晰度的 `representation` 及其 `backupUrl`（约 256–295 行）。
- 坑：必须按跳转后的 photoId 匹配，否则会下到推荐流；风控页要稍后重试或用有界面的浏览器。

### 微博（`scripts/platforms/weibo.js`）

- 链接只认两种：`video.weibo.com/show?fid=1034:<数字>`、`weibo.com/tv/show/1034:<数字>`。
- 数据来源：截获 `/tv/api/component` 接口（约 9、70–97 行），只收 `weibocdn.com` 的地址。
- 坑：
  - 接口 `msg` 含「暂无权限」「无权查看」「仅自己可见」时是永久失败，不重试。
  - 页面出现「验证码」「安全验证」「访问频次」「请先登录」或跳到 `passport.weibo` 是访客验证，要稍后重试或用有界面的浏览器（约 169 行）。

## 暂不采用的做法

| 做法 | 不采用的原因 | 什么时候再考虑 |
|---|---|---|
| Agent 校对稿子：机器转写原文保留在 JSON，agent 校对后另存 TXT | 增加流程；先看实际错字多不多 | 稿子里的人名、术语错得多，影响使用时 |
| 批量下载、断点续跑、失败指数退避重试 | 目前一次处理几个链接，让 agent 串行跑就够 | 一次要处理几十上百个链接时 |
| 清晰度审计：枚举所有可下载的流，用 ffprobe 校验分辨率、帧率、编码，失败按顺序降级 | 本 skill 的 B站用 yt-dlp 选流，抖音取最高码率，目前够用 | 出现下到低清或坏文件时 |
| `--headed` 有界面模式，遇到验证码由人手动过 | 目前没遇到验证码 | 抖音、微博、快手频繁要求验证时 |
| B站用 Playwright 抓流 | 它自己说明不登录可能只有 480P；yt-dlp 不登录能到 1080P | 不采用 |
| faster-whisper 转写 | Mac 上没有 CUDA 会退到 small + CPU，中文不如 Qwen3-ASR；也不出逐句 SRT | 不采用 |
