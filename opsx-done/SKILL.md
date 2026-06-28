---
name: opsx-done
description: >
  Finalize an OpenSpec change: verify → archive → git commit → optional merge to main.
  Each step dispatched to a Haiku subagent for context isolation and token savings.
  Use when implementation is complete and reviewed. Trigger with /opsx-done.
---

# opsx-done — OpenSpec 变更收尾

将 verify → archive → git commit → (可选) merge to main 四步机械操作串行分发给 Haiku 子 agent 执行。主 session 上下文不参与，token 消耗最小化。

## 执行流程

### 第零步：确认 change 目录

若用户调用时未指定 change 名称，运行：

```bash
openspec list
```

展示 active changes，请用户确认目标 change 目录名（如 `add-mqtt-filter`）。

确认后记录为 `{change_name}`，对应路径 `openspec/changes/{change_name}/`。

---

### 第一步：Verify（Haiku 子 agent）

派发 Agent（model: haiku），prompt：

```
你是 OpenSpec 助手。工作目录：{当前项目根目录}。
任务：对 change 目录 openspec/changes/{change_name} 运行 verify。

步骤：
1. Read openspec/changes/{change_name}/tasks.md
2. Read openspec/changes/{change_name}/specs/ 下的所有 spec 文件
3. 逐项核对 tasks.md 中每个任务的完成状态
4. 检查 specs/ 与代码实现的一致性
5. 将结果写入 openspec/changes/{change_name}/verify-report.md
6. 最后输出一行结论：PASS 或 FAIL（附原因）

先 Read 再 Edit，不要跳过读取直接写入。
```

- **PASS** → 继续第二步
- **FAIL** → 停止，展示原因，等用户修复后重新触发

---

### 第二步：Archive（Haiku 子 agent）

派发 Agent（model: haiku），prompt：

```
你是 OpenSpec 助手。工作目录：{当前项目根目录}。
任务：归档已完成的 change：openspec/changes/{change_name}。

步骤：
1. Read openspec/INDEX.md
2. 将 openspec/changes/{change_name}/ 整个目录移动到 openspec/archive/（目录名格式：YYYYMMDD-{change_name}，日期取今天）
3. 更新 openspec/INDEX.md，将该 change 从 active 移到 archived 区域
4. 输出归档后的完整路径

先 Read 再 Edit。
```

---

### 第三步：Git Commit（Haiku 子 agent）

派发 Agent（model: haiku），prompt：

```
你是 Git 助手。工作目录：{当前项目根目录}。
任务：只暂存并提交本次 OpenSpec change（{change_name}）相关的文件。

步骤：
1. git status（查看当前状态）
2. git add openspec/
   （覆盖：归档目录 openspec/archive/ + openspec/INDEX.md 等所有 openspec/ 下变更）
3. git add -u
   （覆盖：所有已追踪文件的修改，即实现代码；不暂存无关的新增未追踪文件）
4. git diff --staged --name-only（输出暂存文件列表供核对）
5. git diff --staged（读取变更摘要，用于生成 commit message）
6. 根据暂存内容生成 Conventional Commits 格式 commit message（中文描述）：
   - type：feat / fix / refactor / docs / chore 等
   - scope：从变更文件路径推断
   - 描述：动词开头，不超过 50 字
7. git commit -m "{message}"
8. 输出 commit hash 和 message

禁止 git push。
```

---

### 第四步：询问是否 Merge to Main

三步全部成功后，展示摘要并询问：

```
✅ Verify / Archive / Commit 完成。

当前分支：feat/{change_name}
是否合并到 main 分支？

  y   → 执行 merge（推荐：变更已完成且无需 PR 时）
  n   → 跳过，保持当前分支（默认）
```

若用户输入 `y`，派发 Agent（model: haiku），prompt：

```
你是 Git 助手。工作目录：{当前项目根目录}。
任务：将 feat/{change_name} 合并到 main。

步骤：
1. git checkout main
2. git merge feat/{change_name} --no-ff -m "merge(feat): {change_name}"
3. 报告结果

若遇到冲突：
- 不要自动解决
- git merge --abort
- 列出冲突文件，告知用户手动处理后重新合并
```

---

### 第五步：输出最终摘要

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
opsx-done 完成

  Change:  {change_name}
  Verify:  ✅ PASS
  Archive: openspec/archive/{date}-{change_name}/
  Commit:  {hash} — {message}
  Merge:   ✅ main ← feat/{change_name}
           （或）⏭ 跳过
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 设计原则

- **串行执行**：每步失败则中止，不继续后续步骤
- **Haiku 子 agent**：每步独立上下文，主 session cache 不受影响
- **Verify 门禁**：未通过 verify 不归档，不提交
- **不自动 push**：commit 后 push 由用户手动控制
- **merge 询问制**：合并主分支是不可逆操作，必须明确确认
