#!/usr/bin/env bash
# Git 版本标签工具（非交互式，供 Claude skill 调用）
#
# Usage:
#   tag.sh info                          # 输出当前 tag 状态，供 Claude 分析
#   tag.sh create <version>              # 创建轻量 tag（lightweight）
#   tag.sh create <version> <message>    # 创建带说明的 annotated tag
#   tag.sh push <version>                # 推送 tag 到 origin
#   tag.sh delete <version>              # 删除本地 + 远端 tag
#   tag.sh list                          # 列出最近 10 个 tag（含类型）

set -euo pipefail

cmd="${1:-info}"

# ── 解析 semver ───────────────────────────────────────────────
parse_semver() {
    local tag="${1#v}"
    IFS='.' read -r major minor patch <<< "$tag"
    echo "${major:-0} ${minor:-0} ${patch:-0}"
}

# ── 计算下一个版本 ────────────────────────────────────────────
next_version() {
    local latest="$1"
    local bump="$2"
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

case "$cmd" in

    # ── info：输出分析所需的上下文 ──────────────────────────────
    info)
        latest=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || echo "")
        if [[ -n "$latest" ]]; then
            commit_count=$(git rev-list "${latest}..HEAD" --count 2>/dev/null || echo 0)
            commits=$(git log "${latest}..HEAD" --oneline 2>/dev/null || echo "")
        else
            commit_count=$(git rev-list HEAD --count 2>/dev/null || echo 0)
            commits=$(git log --oneline -10 2>/dev/null || echo "")
        fi

        echo "latest_tag=${latest:-（无）}"
        echo "commit_count=${commit_count}"
        echo "next_patch=$(next_version "$latest" patch)"
        echo "next_minor=$(next_version "$latest" minor)"
        echo "next_major=$(next_version "$latest" major)"
        echo "---commits---"
        echo "$commits"
        ;;

    # ── list：列出最近 tag（含类型标注）─────────────────────────
    list)
        while IFS= read -r t; do
            type=$(git cat-file -t "$t" 2>/dev/null)
            if [[ "$type" == "tag" ]]; then
                msg=$(git tag -l --format='%(contents:subject)' "$t" 2>/dev/null | head -1)
                echo "${t}  [annotated] ${msg}"
            else
                echo "${t}  [lightweight]"
            fi
        done < <(git tag --list 'v[0-9]*' --sort=-v:refname | head -10)
        ;;

    # ── create：本地打 tag（支持 lightweight 和 annotated）────────
    create)
        version="${2:-}"
        message="${3:-}"   # 有 message → annotated tag；无 → lightweight tag
        if [[ -z "$version" ]]; then
            echo "错误：请提供版本号，如：tag.sh create v1.2.3 [message]" >&2
            exit 1
        fi
        if git rev-parse "$version" >/dev/null 2>&1; then
            echo "错误：tag $version 已存在" >&2
            exit 1
        fi
        if [[ -n "$message" ]]; then
            git tag -a "$version" -m "$message"
            echo "已创建本地 annotated tag: $version"
            echo "  说明：$message"
        else
            git tag "$version"
            echo "已创建本地 lightweight tag: $version"
        fi
        ;;

    # ── push：推送 tag 到远端 ──────────────────────────────────
    push)
        version="${2:-}"
        if [[ -z "$version" ]]; then
            echo "错误：请提供版本号，如：tag.sh push v1.2.3" >&2
            exit 1
        fi
        git push origin "$version"
        echo "已推送 tag: $version → origin"
        ;;

    # ── delete：删除本地 + 远端 tag ────────────────────────────
    delete)
        version="${2:-}"
        if [[ -z "$version" ]]; then
            echo "错误：请提供版本号，如：tag.sh delete v1.2.3" >&2
            exit 1
        fi
        git tag -d "$version" 2>/dev/null && echo "本地已删除: $version" || echo "本地不存在: $version"
        git push origin --delete "$version" 2>/dev/null && echo "远端已删除: $version" || echo "远端不存在: $version"
        ;;

    *)
        echo "用法: tag.sh [info|list|create <ver>|push <ver>|delete <ver>]" >&2
        exit 1
        ;;
esac
