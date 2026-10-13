# 迁移到 v2：公开仓历史已重建

从这次发布起，`laodao-ai/laodao-skills` 的开发迁到了私有仓 `laodao-ai/laodao-skills-dev`，
公开仓的内容改由发布快照重建，与旧历史没有共同祖先。已有安装继续用 `/laodao-upgrade`
只会报「本地 main 与 origin/main 已分叉」——升级脚本无法跨越这条断层，只能靠本文档手动迁移一次。

下面命令以 README 安装步骤的默认 checkout 位置 `~/.claude/skills/laodao-skills` 为例；
如果你当初 clone 到了别的目录，把命令里的路径换成你自己的实际位置。

## 迁移步骤

1. 确认本地无改动、无未推提交：

   ```bash
   cd ~/.claude/skills/laodao-skills
   git status --short
   ```

   应无输出，有输出先提交或确认可以丢弃。

   再检查有没有本地已提交但没推送的改动。如果你**还没有**运行过 `/laodao-upgrade`
   （还没见过「已分叉」提示）：

   ```bash
   git log --oneline origin/main..HEAD
   ```

   应无输出；有输出说明有未推送的本地提交，先推送或确认可以丢弃。

   如果你**已经**运行过 `/laodao-upgrade` 并看到过「已分叉」提示：这时本地的 `origin/main`
   已经被那次 `fetch` 指向了新公开仓的历史，和上面这条命令再一起用会把整段旧开发历史误判成
   「未推送」。改用下面这条，取 `origin/main` 在那次 fetch 之前的位置（reflog 里的上一个值）作对比：

   ```bash
   git log --oneline 'origin/main@{1}..HEAD'
   ```

   应无输出；有输出才是真正未推送的本地提交。

   > 如果「已分叉」之后你又手动 `fetch`/`pull` 过不止一次，`@{1}` 不一定还是分叉发生前那一刻。
   > 用 `git reflog show origin/main` 找到最早把 `origin/main` 从旧历史切到新历史的那条记录，
   > 把 `@{1}` 换成它在 reflog 里的序号。

2. 把旧目录改名为带时间戳的备份，不要直接删除：

   ```bash
   cd ~/.claude/skills
   mv laodao-skills "laodao-skills.bak-$(date +%Y%m%d%H%M%S)"
   ```

3. 重新 clone 到原来的位置：

   ```bash
   git clone https://github.com/laodao-ai/laodao-skills.git ~/.claude/skills/laodao-skills
   ```

4. 运行 setup，把 `~/.claude/skills`、`~/.agents/skills` 下的链接指向新 checkout
   （并清理仍留在 `~/.codex/skills` 的本仓旧安装项）：

   ```bash
   cd ~/.claude/skills/laodao-skills
   bash setup.sh
   ```

5. 验证升级已恢复正常：

   ```
   /laodao-upgrade
   ```

   应输出「已是最新版本」而不是「已分叉」。

6. 确认第 4、5 步都成功后，再删除第 2 步产生的备份目录。
