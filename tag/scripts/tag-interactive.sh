#!/usr/bin/env bash
# Git 版本标签：创建 & 推送
#
# Usage:
#   ./hack/tag.sh              # 自动从上一个 tag 推断，patch +1（lightweight）
#   ./hack/tag.sh minor        # minor +1
#   ./hack/tag.sh major        # major +1
#   ./hack/tag.sh v1.5.0       # 直接指定版本号
#   ./hack/tag.sh --annotated  # 创建带说明的 annotated tag（可与版本参数组合）
#   ./hack/tag.sh --list       # 列出最近 10 个 tag（含类型）
#   ./hack/tag.sh --delete v0.1.0  # 删除本地+远端 tag
#
# 示例（annotated tag）：
#   ./hack/tag.sh --annotated              # patch +1，交互式输入说明
#   ./hack/tag.sh minor --annotated        # minor +1，交互式输入说明
#   ./hack/tag.sh v2.0.0 --annotated       # 指定版本，交互式输入说明

set -euo pipefail

# ── 解析参数（支持任意顺序）─────────────────────────────────
ANNOTATED=false
POSITIONAL_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --annotated) ANNOTATED=true ;;
        *) POSITIONAL_ARGS+=("$arg") ;;
    esac
done
set -- "${POSITIONAL_ARGS[@]+"${POSITIONAL_ARGS[@]}"}"

# ── 列出 tag ──────────────────────────────────────────────────
if [[ "${1:-}" == "--list" ]]; then
    echo "最近 tag："
    while IFS= read -r t; do
        type=$(git cat-file -t "$t" 2>/dev/null)
        if [[ "$type" == "tag" ]]; then
            msg=$(git tag -l --format='%(contents:subject)' "$t" 2>/dev/null | head -1)
            echo "  ${t}  [annotated] ${msg}"
        else
            echo "  ${t}  [lightweight]"
        fi
    done < <(git tag --list 'v[0-9]*' --sort=-v:refname | head -10)
    exit 0
fi

# ── 删除 tag ──────────────────────────────────────────────────
if [[ "${1:-}" == "--delete" ]]; then
    tag="${2:-}"
    if [[ -z "$tag" ]]; then
        echo "错误：请指定要删除的 tag，如：$0 --delete v0.1.0"
        exit 1
    fi
    echo "即将删除 tag: $tag（本地 + 远端）"
    read -rp "确认？(y/N) " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "已取消"
        exit 0
    fi
    git tag -d "$tag" 2>/dev/null && echo "  本地已删除" || echo "  本地不存在"
    git push origin --delete "$tag" 2>/dev/null && echo "  远端已删除" || echo "  远端不存在"
    exit 0
fi

# ── 获取上一个 tag ────────────────────────────────────────────
latest=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || echo "")

# ── 解析版本号 ────────────────────────────────────────────────
parse_semver() {
    local tag="$1"
    # 去掉 v 前缀，按 . 拆分
    local ver="${tag#v}"
    IFS='.' read -r major minor patch <<< "$ver"
    echo "${major:-0} ${minor:-0} ${patch:-0}"
}

# ── 计算下一个版本 ────────────────────────────────────────────
next_version() {
    local bump="${1:-patch}"
    if [[ -z "$latest" ]]; then
        echo "v0.1.0"
        return
    fi

    read -r major minor patch <<< "$(parse_semver "$latest")"
    case "$bump" in
        major) echo "v$((major + 1)).0.0" ;;
        minor) echo "v${major}.$((minor + 1)).0" ;;
        patch) echo "v${major}.${minor}.$((patch + 1))" ;;
    esac
}

# ── 确定目标版本 ──────────────────────────────────────────────
arg="${1:-patch}"

case "$arg" in
    patch|minor|major)
        new_tag=$(next_version "$arg")
        ;;
    v[0-9]*)
        # 直接指定版本号
        new_tag="$arg"
        ;;
    *)
        echo "用法: $0 [patch|minor|major|v版本号|--list|--delete <tag>] [--annotated]"
        echo ""
        echo "  patch           patch +1（默认，lightweight tag）"
        echo "  minor           minor +1"
        echo "  major           major +1"
        echo "  v1.2.3          直接指定版本"
        echo "  --annotated     创建带说明的 annotated tag（可与版本参数组合）"
        echo "  --list          列出最近 tag（含类型）"
        echo "  --delete TAG    删除 tag"
        exit 1
        ;;
esac

# ── 检查 tag 是否已存在 ───────────────────────────────────────
if git rev-parse "$new_tag" >/dev/null 2>&1; then
    echo "错误：tag $new_tag 已存在"
    exit 1
fi

# ── 显示变更摘要 ──────────────────────────────────────────────
echo ""
if [[ -n "$latest" ]]; then
    echo "上一个 tag：$latest"
    commit_count=$(git rev-list "${latest}..HEAD" --count)
    echo "新增提交数：$commit_count"
else
    echo "无历史 tag（首次打标签）"
fi
tag_type_label="lightweight"
$ANNOTATED && tag_type_label="annotated"
echo "新版本标签：$new_tag  [${tag_type_label}]"
echo ""

# 显示提交列表
if [[ -n "$latest" ]]; then
    echo "包含的提交："
    git log "${latest}..HEAD" --oneline | while read -r line; do echo "  $line"; done
else
    echo "包含的提交："
    git log --oneline -10 | while read -r line; do echo "  $line"; done
    echo "  ...（仅显示最近 10 条）"
fi
echo ""

# ── Annotated tag：收集说明文字 ──────────────────────────────
TAG_MESSAGE=""
if $ANNOTATED; then
    echo "请输入 tag 说明（一行简短描述，直接回车使用自动生成内容）："
    if [[ -n "$latest" ]]; then
        auto_msg="Release ${new_tag}"
    else
        auto_msg="Initial release ${new_tag}"
    fi
    echo "  自动内容：${auto_msg}"
    read -rp "  说明> " user_msg
    TAG_MESSAGE="${user_msg:-$auto_msg}"
    echo ""
    echo "  将使用说明：${TAG_MESSAGE}"
    echo ""
fi

# ── 确认 ──────────────────────────────────────────────────────
read -rp "确认创建并推送 $new_tag？(Y/n) " confirm
if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
    echo "已取消"
    exit 0
fi

# ── 创建 & 推送 ──────────────────────────────────────────────
if $ANNOTATED; then
    git tag -a "$new_tag" -m "$TAG_MESSAGE"
    echo "已创建 annotated tag: $new_tag"
    echo "  说明：$TAG_MESSAGE"
else
    git tag "$new_tag"
    echo "已创建 lightweight tag: $new_tag"
fi

git push origin "$new_tag"
echo "已推送 tag: $new_tag → origin"
