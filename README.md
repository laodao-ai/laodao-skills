# laodao-skills

老刀AI码场自建 Claude Code Skills 统一管理仓库。

## Skills 列表

| 分类 | Skill | 说明 |
|------|-------|------|
| 内容创作 | bilibili-research | B站搜索词调研与选题分析 |
| 内容创作 | x-research | X/Twitter 调研 |
| 内容创作 | youtube-research | YouTube 调研 |
| 内容创作 | zhihu-research | 知乎调研 |
| 开发工具 | commit-message | Git commit 信息生成 |
| 开发工具 | ssh-tunnel | SSH 隧道管理 |
| 开发工具 | tag | Git 语义化版本标签 |
| 开发工具 | gstack-init | gstack 项目级文档归集 |
| OpenSpec | opsx-maintain | OpenSpec 目录维护 |
| OpenSpec | opsx-roadmap-planner | 分阶段 roadmap 规划工作流 |
| 嵌入式 | embedded-lint | C 语言静态分析 |
| 嵌入式 | embedded-test-sop | 嵌入式手动测试 SOP 生成 |
| 文档转换 | docx2md | Word 转 Markdown |
| 文档转换 | pdf2md | PDF 转 Markdown |
| 文档转换 | xlsx2md | Excel 转 CSV |
| 元工具 | **config-skills** | **按场景一键配置 skillOverrides（详见下方专章）** |
| 元工具 | update | 更新 laodao-skills |

## 安装

```bash
cd ~/.claude/skills
git clone https://github.com/laodao-ai/laodao-skills.git
cd laodao-skills
bash setup.sh
```

## 更新

在 Claude Code 中直接使用：

```
/ld-update
```

或手动更新：

```bash
cd ~/.claude/skills/laodao-skills
git pull
bash setup.sh
```

## 工作原理

- **Linux/macOS**：setup.sh 在 `~/.claude/skills/` 下为每个 skill 创建相对路径 symlink
- **Windows**：setup.sh 将 skill 目录复制到 `~/.claude/skills/`，并写入 `.laodao-skills` 标记文件用于更新检测

---

## config-skills - 配置 plugin/skill 的元工具

按工作场景一键配置项目级 `.claude/settings.json` 的 `skillOverrides` 字段，无需手动编辑。

### 4 套 Preset

| Preset | 适用场景 | 探测特征 | ON 数量 |
|--------|----------|----------|---------|
| `content-creation` | 写文章、博客、做封面/配图、SDD | `hugo.toml/yaml` | ~21 |
| `go-dev` | Go 后端、CLI 项目 | `go.mod` | ~24 |
| `embedded-dev` | 嵌入式 C/MCU 固件 | `CMakeLists.txt` 或 `.c/.h` | ~28 |
| `web-dev` | 前端、全栈、博客 QA | `package.json` + react/vue/next/svelte | ~35 |

四套共享的"基础 ON"：superpowers 核心入口、git commit 类、remember、OpenSpec/SDD 全套。

### 工作流（v3：8 步）

1. **扫描环境 + 自动探测项目类型**：根据特征文件推断 preset
2. **preset 健康检查 + 自动同步**（v3）：检测 missing / phantom，按 12 条智能规则推断默认值
3. 检查 `.claude/settings.json`（不存在则自动建空）
4. 询问用户选 preset（探测命中则推荐第一位）
5. 校验 + 双向 Diff + 幂等检查
6. AskUserQuestion 展示 Diff 让用户确认
7. **备份**（保留最近 3 份 `.bak.YYYYMMDD-HHMMSS`）+ **原子写回**（tmp + replace）
8. 展示分类清单 + 引导修改

### 智能默认值推断（关键词匹配）

新装的 skill 通过 Step 2 自动加入 preset 时，按 skill 名关键词推断各 preset 的默认值：

| 关键词 | content | go-dev | embedded | web | 类型 |
|--------|:-------:|:------:|:--------:|:---:|------|
| `git/release` | on | on | on | on | git 类核心 |
| `lint/code-review/TDD/feature-dev` | off | on | on | on | 代码工程 |
| `humanizer/tech-writing` | on | off | off | u-i-o | 内容创作 |
| `embedded/firmware/mcu` | off | off | on | off | 嵌入式 |
| `frontend/ui-ux/react/vue` | u-i-o | off | off | on | 前端 UI |
| `qa/playwright/chrome-devtools` | u-i-o | u-i-o | off | on | 浏览器 QA |
| 未匹配 fallback | u-i-o | u-i-o | u-i-o | u-i-o | 安全保留入口 |

完整 12 条规则见 `config-skills/SKILL.md`。

### 安全特性

- **备份机制**：每次写 settings.json 前自动 `.bak.YYYYMMDD-HHMMSS`，保留最近 3 份
- **原子写回**：`tmp` 文件 + `os.replace`，防止写一半崩溃损坏文件
- **双向 Diff**：检测"preset 加了什么"+"settings 多余的会被删什么"
- **幂等检查**：已 up-to-date 提前结束，不做无意义改动
- **Skill ID 校验**：preset 列了但本地没装的 phantom，跳过且报告

### 用法

```
/config-skills
```

或自然触发："切换到 Go 模式"、"配 settings.json"、"skill 太多了清理一下"等。

详见 `config-skills/SKILL.md`。

---

## 许可

MIT
