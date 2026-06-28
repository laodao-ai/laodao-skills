#!/usr/bin/env python3
"""init.py — 把 openspec/workflow/ bundle 铺进一个项目（或更新已铺过的项目）。

skill `opsx-project-init` 的执行核心。权威源 = 本 skill 的 assets/workflow/（单一源）。
两种模式：
  init   —— 空项目首次铺设：建目录骨架、拷 bundle、从模版生成 config.yaml、注入
           INDEX.md / CLAUDE.md / AGENTS.md 的托管区块。
  update —— 已铺过的项目重拉最新 bundle：覆盖 workflow/ 托管文件、重注入托管区块；
           **不动 config.yaml 的本项目段、不覆盖用户内容**。

确定性操作交脚本（拷贝、建目录、标记区块幂等注入）；需判断的（填 config 的「本项目」段、
合并已存在的 config.yaml）留给模型，见 SKILL.md。

标记区块（HTML 注释包裹，幂等替换；用户勿手改区块内）：
  CLAUDE.md / AGENTS.md : <!-- opsx-init:start --> ... <!-- opsx-init:end -->
  INDEX.md             : <!-- opsx-init:rules:start --> ... <!-- opsx-init:rules:end -->

用法见 `python init.py --help`。
"""

import argparse
import os
import shutil
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SKILL_DIR, "assets")
BUNDLE_SRC = os.path.join(ASSETS, "workflow")
SNIPPETS = os.path.join(ASSETS, "snippets")

MARK_DOC = ("<!-- opsx-init:start —— 由 opsx-project-init 维护，勿手改本区块 -->",
            "<!-- opsx-init:end -->")
MARK_IDX = ("<!-- opsx-init:rules:start —— 由 opsx-project-init 维护，勿手改本区块 -->",
            "<!-- opsx-init:rules:end -->")

CORE_DIRS = ["changes", "specs"]  # openspec 核心；buglists/todolists 由各自 recorder skill 首用时建


# ── 标记区块幂等注入 ─────────────────────────────────────────

def inject(path, start, end, content, header=""):
    """有标记则替换标记间内容；无标记则追加；文件不存在则以 header 起头新建。返回动作描述。"""
    block = f"{start}\n{content.rstrip()}\n{end}\n"
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        if start in text and end in text:
            pre = text[:text.index(start)]
            post = text[text.index(end) + len(end):]
            new = pre + block.rstrip("\n") + post.lstrip("\n")
            if not new.endswith("\n"):
                new += "\n"
            action = "更新托管区块"
        else:
            new = text.rstrip("\n") + "\n\n" + block
            action = "追加托管区块"
    else:
        new = (header.rstrip("\n") + "\n\n" if header else "") + block
        action = "新建并写入"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return action


def read_snippet(name):
    return open(os.path.join(SNIPPETS, name), encoding="utf-8").read()


# ── bundle 铺设 ──────────────────────────────────────────────

def copy_bundle(root):
    dst = os.path.join(root, "openspec", "workflow")
    shutil.copytree(BUNDLE_SRC, dst, dirs_exist_ok=True)
    n = sum(len(fs) for _, _, fs in os.walk(dst))
    return dst, n


def ensure_dirs(root):
    made = []
    for d in CORE_DIRS:
        p = os.path.join(root, "openspec", d)
        if not os.path.isdir(p):
            os.makedirs(p, exist_ok=True)
            open(os.path.join(p, ".gitkeep"), "a").close()
            made.append(f"openspec/{d}/")
    return made


def handle_config(root, mode):
    """init: 缺则从模版生成，存在则报告需合并。update: 不动。返回 (状态, 提示)。"""
    cfg = os.path.join(root, "openspec", "config.yaml")
    tmpl = os.path.join(root, "openspec", "workflow", "config.template.yaml")
    if mode == "update":
        return ("skip", "update 不动 config.yaml（如模版有变，模型按需合并通用段/rules）")
    if os.path.exists(cfg):
        return ("exists", "config.yaml 已存在 → 模型合并「通用」context 段 + rules，保留「本项目」段与用户键")
    shutil.copyfile(tmpl, cfg)
    return ("created", "已从 config.template.yaml 生成 config.yaml → 填写「本项目」context 段")


# ── 主流程 ──────────────────────────────────────────────────

def run(root, mode):
    osroot = os.path.join(root, "openspec")
    if mode == "init":
        os.makedirs(osroot, exist_ok=True)
    elif not os.path.isdir(osroot):
        _die("openspec/ 不存在——update 需在已铺设的项目里跑；空项目请用 init")

    report = []
    made = ensure_dirs(root)
    if made:
        report.append("建目录：" + " ".join(made))

    dst, n = copy_bundle(root)
    report.append(f"铺 bundle：openspec/workflow/（{n} 文件，{'覆盖' if mode=='update' else '写入'}）")

    cstat, cmsg = handle_config(root, mode)
    report.append(f"config.yaml：{cmsg}")

    # INDEX.md 托管区块
    idx = os.path.join(osroot, "INDEX.md")
    a = inject(idx, *MARK_IDX, read_snippet("index-section.md"),
               header="# OpenSpec Index\n\n本文件是当前仓库 OpenSpec 资产索引。")
    report.append(f"openspec/INDEX.md：{a}")

    # CLAUDE.md / AGENTS.md 托管区块
    sec = read_snippet("claude-section.md")
    for fn in ("CLAUDE.md", "AGENTS.md"):
        p = os.path.join(root, fn)
        a = inject(p, *MARK_DOC, sec,
                   header=f"# {fn.split('.')[0]}\n\n本文件为项目级 AI 指令。")
        report.append(f"{fn}：{a}")

    print(f"✓ opsx-project-init {mode} 完成 @ {os.path.abspath(root)}\n")
    for r in report:
        print("  - " + r)
    if cstat in ("created", "exists"):
        print("\n下一步（模型/人工）：")
        if cstat == "created":
            print("  · 编辑 openspec/config.yaml 的「## 本项目」context 段，填本项目 tech stack/约定")
        else:
            print("  · 合并 openspec/config.yaml：把模版的「通用」context 段 + rules 并入，保留你的「本项目」段")
        print("  · 安装配套 skill：bash ~/.skills/laodao-skills/setup.sh（/spec-review /impl-review /opsx-done）")


def _die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="把 openspec/workflow bundle 铺进项目")
    p.add_argument("mode", choices=["init", "update"], help="init=首次铺设 / update=重拉最新 bundle")
    p.add_argument("--root", default=".", help="目标项目根（默认当前目录）")
    args = p.parse_args()
    run(args.root, args.mode)


if __name__ == "__main__":
    main()
