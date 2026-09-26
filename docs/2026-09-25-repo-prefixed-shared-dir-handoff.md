# Handoff：安装落点按仓隔离（laodao-skills 侧）

> 来源：pg-ops 仓 2026-09-25 讨论。pg-ops / db-llm 两仓正在把共用目录 `shared/` 改为仓名前缀目录。
> 本文记录跨仓约定，以及本仓的核查结论。

## 约定（2026-09-25，人拍板）

同一台机器上装多套 skill 仓时，各仓的安装落点 MUST 互不重叠：

- 宿主目录（`~/.claude/skills/`、`~/.codex/skills/`）里，除 skill 目录外，
  各仓不放任何共用名字的东西（如 `shared/`、`lib/`、`common/`）。
- 确需放非 skill 的支撑目录时，目录名 MUST 带仓名前缀（如 `pg-ops-shared/`），且由本仓独占：
  自属标记 → 整份替换；非自属 → 拒装。
- 仓内目录名与安装落点同名，保证一条相对路径在 Unix 软链和 Windows 拷贝两种安装下都可达。

## 触发这条约定的问题

pg-ops 与 db-llm 的 skill 脚本都用 `scripts/../../shared` 引用本仓 `shared/`。
Windows 拷贝安装时两仓都落到 `<宿主>/shared`，只能靠「合并拷贝」共处，
所有权标记互相冲突：先装 pg-ops 再装 db-llm，db-llm 会拒装退出。

## 本仓核查结论（2026-09-25）：无需改动

- `setup.sh` 只把含 `SKILL.md` 的目录装进宿主 skill 目录，没有 shared 类共用目录。
- Windows 拷贝带 `.laodao-skills` 标记，非自属同名目录跳过不覆盖；Unix 非自属软链也不覆盖。
- 没有 skill 用 `../../` 引用 skill 目录以外的东西。

## 相关但不在本次范围

本仓 skill 名不带前缀（如 `tag`、`pdf2md`、`commit-message`），和其它套件重名时会被跳过、装不上。
这是 skill 命名空间问题，与共用目录无关。已有调研见 `docs/skill-namespace-research.md`
（结论：要带前缀须走 plugin 机制）。

## 以后要注意的点

新增需要多个 skill 共用的脚本时，建带 `laodao-` 前缀的支撑目录，或放进各 skill 自己目录里。
不要在宿主 skill 目录里新建不带前缀的共用目录。
