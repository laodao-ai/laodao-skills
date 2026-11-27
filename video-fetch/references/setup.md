# 安装与环境适配

本文写本 skill 依赖什么、怎么装、装在哪、换环境时改哪里。

## 平台要求

- 下载（B站、抖音）：macOS、Linux 都可以。
- 转写：只支持 Apple Silicon（M 系列芯片）的 Mac，因为用的是 mlx-audio。用 `uname -m` 检查，输出 `arm64` 即可。
- 其他机器只能加 `--no-asr`，只下载不转写。不加的话转写会失败，退出码为 2。

## 依赖清单

| 依赖 | 用途 | 安装 | 检查 |
|---|---|---|---|
| uv | 运行脚本，按脚本头自动装 Python 依赖 | `brew install uv` | `uv --version` |
| ffmpeg、ffprobe | 合并音视频、抽音频、切音频、检查音视频流 | `brew install ffmpeg`（ffprobe 一起装上） | `ffmpeg -version` |
| Google Chrome | 抖音的无头浏览器（优先用） | 正常安装 Chrome | `ls "/Applications/Google Chrome.app"` |
| Playwright 的 Chromium | 没有 Chrome 时代替它 | `uv run --with playwright==1.65.2 playwright install chromium` | 抖音能下载即可 |
| Python 包 | yt-dlp、playwright、mlx-audio | 不用手动装，`uv run` 首次运行自动装 | — |
| 转写模型 | 语音识别、逐字对齐 | 首次转写时自动下载，也可以提前放好，见下节 | — |

Python 包的版本钉在脚本头里：`scripts/fetch.py` 依赖 yt-dlp 和 playwright，`scripts/transcribe.py` 依赖 mlx-audio。

## 转写模型

两个模型，都来自 Hugging Face 的 mlx-community，合计约 3.5 GB：

| 模型 | 大小 | 用途 |
|---|---|---|
| `Qwen3-ASR-1.7B-8bit` | 约 2.3 GB | 语音转文字，带标点 |
| `Qwen3-ForcedAligner-0.6B-8bit` | 约 1.2 GB | 给每个字标时间 |

`scripts/transcribe.py` 按下面的顺序找模型。在某个目录里两个模型子目录都存在，才用这个目录：

1. 环境变量 `VIDEO_FETCH_MODELS_DIR` 指向的目录
2. `~/.omlx/models/mlx-community`
3. `/Users/Shared/.omlx/models/mlx-community`
4. 都没有：从 Hugging Face 下载到 Hugging Face 缓存

本机已经有这两个模型、但放在别处时，二选一：

- 设置 `VIDEO_FETCH_MODELS_DIR`。注意 agent 的 shell 一般不读 `~/.zshrc`，只在那里 export 不生效。Claude Code 要写进 `~/.claude/settings.json`：

  ```json
  { "env": { "VIDEO_FETCH_MODELS_DIR": "/你的/模型/目录" } }
  ```

- 不设环境变量，把模型目录软链到第 2 个位置：

  ```bash
  mkdir -p ~/.omlx/models
  ln -s /你的/模型/目录 ~/.omlx/models/mlx-community
  ```

## 下载的东西放在哪

| 内容 | 默认位置 | 换位置用的环境变量 |
|---|---|---|
| uv 装的 Python 包 | `~/.cache/uv`（`uv cache dir` 可查） | `UV_CACHE_DIR` |
| 从 Hugging Face 下载的模型 | `~/.cache/huggingface` | `HF_HOME` |
| Playwright 的 Chromium | macOS 为 `~/Library/Caches/ms-playwright` | `PLAYWRIGHT_BROWSERS_PATH` |
| 下载的视频和稿子 | 当前目录下 `<平台>-<视频ID>/` | 运行时加 `--output` |

这几个环境变量和 `VIDEO_FETCH_MODELS_DIR` 一样，要在 agent 能读到的地方设置。

## 网络

需要能访问：

- B站、抖音
- PyPI：首次运行装 Python 包
- Hugging Face：本机没有模型时下载。国内网络访问慢时，可以设 `HF_ENDPOINT` 指向 Hugging Face 镜像站

## 首次运行

- 首次运行要装 Python 包，转写还可能要下载模型，会比平时慢很多，这不是卡住。
- 之后都用缓存，一个 12 分钟的视频连下载带转写约半分钟到一分钟。
