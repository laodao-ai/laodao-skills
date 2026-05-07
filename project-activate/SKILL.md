# /project-activate

按项目类型激活合适的 Claude Code 工具集（plugins + MCP + skills 提示）。

**触发条件**：用户输入 `/project-activate`

---

## 执行流程

### Step 1：读取全局配置

运行以下命令获取当前 `enabledPlugins` 状态（true = 已启用，false = 已禁用）：

```bash
python3 -c "
import json, os
p = os.path.expanduser('~/.claude/settings.json')
d = json.load(open(p))
ep = d.get('enabledPlugins', {})
enabled = [k for k,v in ep.items() if v]
disabled = [k for k,v in ep.items() if not v]
print('ENABLED:', json.dumps(enabled, ensure_ascii=False))
print('DISABLED:', json.dumps(disabled, ensure_ascii=False))
"
```

记录当前已启用的插件列表，用于后续 diff 计算。

---

### Step 2：确定目标配置

#### 情况 A：存在 `.claude/profile.json`

读取当前工作目录下的 `.claude/profile.json`：

```bash
python3 -c "import json; print(json.dumps(json.load(open('.claude/profile.json')), indent=2, ensure_ascii=False))"
```

如果 `profile.json` 含 `extends` 字段，加载对应模板并与 profile 差量合并：

```bash
python3 -c "
import json, os

profile = json.load(open('.claude/profile.json'))
template_name = profile.get('extends', '')
template = {}

if template_name:
    tpl_path = os.path.expanduser(f'~/.claude/project-templates/{template_name}.json')
    if os.path.exists(tpl_path):
        template = json.load(open(tpl_path))
    else:
        print(f'WARNING: 模板文件不存在: {tpl_path}')

# 合并：模板 + profile 差量（add 去重，remove 去重）
merged_add = list(set(template.get('plugins', {}).get('add', []) + profile.get('plugins', {}).get('add', [])))
merged_remove = list(set(template.get('plugins', {}).get('remove', []) + profile.get('plugins', {}).get('remove', [])))
merged_mcp = {**template.get('mcp', {}), **profile.get('mcp', {})}
merged_skills = list(set(template.get('skills', []) + profile.get('skills', [])))

print('MERGED_ADD:', json.dumps(merged_add, ensure_ascii=False))
print('MERGED_REMOVE:', json.dumps(merged_remove, ensure_ascii=False))
print('MERGED_MCP:', json.dumps(merged_mcp, ensure_ascii=False))
print('MERGED_SKILLS:', json.dumps(merged_skills, ensure_ascii=False))
"
```

#### 情况 B：不存在 `profile.json`，执行自动探测

按以下优先级顺序检查项目根目录的特征文件，推断项目类型：

```bash
python3 -c "
import os, json, glob

cwd = os.getcwd()
files = os.listdir(cwd)

detected = None
reason = ''

if 'go.mod' in files:
    detected = 'go'
    reason = '检测到 go.mod'
elif 'CMakeLists.txt' in files or any(f.endswith('.c') or f.endswith('.h') for f in files):
    detected = 'embedded-c'
    reason = '检测到 CMakeLists.txt 或 .c/.h 文件'
elif 'project.config.json' in files:
    detected = 'miniprogram'
    reason = '检测到 project.config.json（微信小程序标志）'
elif 'hugo.toml' in files or 'hugo.yaml' in files:
    detected = 'content-blog'
    reason = '检测到 hugo.toml / hugo.yaml'
elif 'package.json' in files:
    try:
        pkg = json.load(open(os.path.join(cwd, 'package.json')))
        deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
        if any(k in deps for k in ['vue', 'react', 'next', 'nuxt', '@vue', '@react']):
            detected = 'frontend'
            reason = '检测到 package.json 含 vue/react/next/nuxt'
    except:
        pass
elif 'requirements.txt' in files or 'pyproject.toml' in files:
    detected = 'data-analysis'
    reason = '检测到 requirements.txt / pyproject.toml'

if detected:
    print(f'DETECTED: {detected}')
    print(f'REASON: {reason}')
else:
    print('DETECTED: none')
    print('REASON: 未匹配到已知特征文件')
"
```

- 如果探测成功，**告知用户探测结果**，例如：「检测到 Go 项目（go.mod），推荐模板：`go`」
- 如果探测失败（`none`），展示所有可用模板供用户选择：

```bash
ls ~/.claude/project-templates/
```

  列出模板后，询问用户选择哪个模板。

加载对应模板文件：

```bash
python3 -c "import json, os; print(json.dumps(json.load(open(os.path.expanduser('~/.claude/project-templates/<TEMPLATE_NAME>.json'))), indent=2, ensure_ascii=False))"
```

---

### Step 3：校验 Plugin ID 有效性

对比「目标 add 列表」中的每个 plugin ID 是否在当前 `settings.json` 的 `enabledPlugins` 字典中存在（无论 true/false）。不存在的 ID 说明该插件未安装，**跳过并警告**：

```bash
python3 -c "
import json, os

settings = json.load(open(os.path.expanduser('~/.claude/settings.json')))
all_known = set(settings.get('enabledPlugins', {}).keys())

to_add = <MERGED_ADD_LIST>  # 替换为实际列表
invalid = [p for p in to_add if p not in all_known]
valid = [p for p in to_add if p in all_known]

if invalid:
    print('WARN: 以下插件未安装，已跳过:', invalid)
print('VALID_ADD:', valid)
"
```

---

### Step 4：计算 Diff 并执行幂等检查

计算实际需要变更的插件（对比当前状态）：

```bash
python3 -c "
import json, os

settings = json.load(open(os.path.expanduser('~/.claude/settings.json')))
current_enabled = {k for k,v in settings.get('enabledPlugins', {}).items() if v}

target_add = set(<VALID_ADD_LIST>)   # 替换为校验后的 add 列表
target_remove = set(<MERGED_REMOVE_LIST>)  # 替换为合并后的 remove 列表

will_add = [p for p in target_add if p not in current_enabled]
will_remove = [p for p in target_remove if p in current_enabled]

if not will_add and not will_remove:
    print('STATUS: already_up_to_date')
else:
    print('STATUS: needs_update')
    print('WILL_ADD:', json.dumps(will_add, ensure_ascii=False))
    print('WILL_REMOVE:', json.dumps(will_remove, ensure_ascii=False))
"
```

**如果 `STATUS: already_up_to_date`**：
> 配置已为最新，无需更新。当前 enabledPlugins 已与 profile 一致。

**直接结束，不执行后续步骤。**

---

### Step 5：展示 Diff 并请求用户确认

向用户展示以下信息（以清晰格式）：

```
⚠️  注意：enabledPlugins 为全局配置，修改后所有当前运行的 Claude Code 会话均受影响。

📦 即将变更 Plugins：
  + 将启用：<WILL_ADD 列表，每行一个>
  - 将禁用：<WILL_REMOVE 列表，每行一个>

🔌 MCP 变更：<如有则展示，否则显示"无">

📚 推荐 Skills（可在对话中直接调用）：<MERGED_SKILLS 列表>

确认应用以上配置？（确认 / 取消 / 说明调整，如"去掉 playwright，加 firecrawl"）
```

**等待用户响应：**
- 用户说「确认」或类似肯定回应 → 继续 Step 6
- 用户取消 → 输出「已取消，未修改任何配置」并结束
- 用户说明调整 → 根据调整更新 will_add/will_remove，重新展示 diff，再次等待确认

---

### Step 6：应用配置

#### 6.1 备份并 Patch settings.json

```bash
python3 -c "
import json, os, shutil, datetime, glob

settings_path = os.path.expanduser('~/.claude/settings.json')
d = json.load(open(settings_path))

# 时间戳备份，保留最近 3 份
ts = datetime.datetime.now().strftime('%Y%m%d-%H%M')
bak_path = settings_path + '.bak.' + ts
shutil.copy2(settings_path, bak_path)
baks = sorted(glob.glob(settings_path + '.bak.*'))
for old in baks[:-3]:
    os.remove(old)

# 应用变更
will_add = <WILL_ADD_LIST>     # 替换为确认后的列表
will_remove = <WILL_REMOVE_LIST>  # 替换为确认后的列表

for pid in will_add:
    d['enabledPlugins'][pid] = True
for pid in will_remove:
    if pid in d['enabledPlugins']:
        d['enabledPlugins'][pid] = False

# 原子写回
tmp = settings_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, settings_path)

print(f'✓ settings.json 已更新，备份: {bak_path}')
"
```

#### 6.2 写入 .mcp.json（仅当 MCP 配置非空时）

如果 `MERGED_MCP` 不为空对象 `{}`，在**项目根目录**写入或合并 `.mcp.json`：

```bash
python3 -c "
import json, os

mcp_path = '.mcp.json'
new_servers = <MERGED_MCP>  # 替换为实际 MCP 配置

existing = {}
if os.path.exists(mcp_path):
    existing = json.load(open(mcp_path))

merged = {**existing.get('mcpServers', {}), **new_servers}
existing['mcpServers'] = merged

with open(mcp_path, 'w') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)
    f.write('\n')
print(f'✓ .mcp.json 已写入')
"
```

#### 6.3 生成 .claude/profile.json（仅首次激活，且项目无 profile.json 时）

```bash
python3 -c "
import json, os

os.makedirs('.claude', exist_ok=True)
profile = {
    'extends': '<TEMPLATE_NAME>',
    'plugins': {'add': [], 'remove': []},
    'mcp': {},
    'skills': []
}
with open('.claude/profile.json', 'w') as f:
    json.dump(profile, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('✓ .claude/profile.json 已生成')
"
```

---

### Step 7：完成提示

输出总结：

```
✅ 项目环境已激活

📦 Plugins 变更：
  + 已启用：<WILL_ADD 列表>
  - 已禁用：<WILL_REMOVE 列表>

📚 本项目推荐 Skills：<MERGED_SKILLS>
   （直接在对话中输入 /skill名称 即可使用）

🔄 Plugin 变更需重启 Claude Code 后生效。
   请关闭当前窗口并重新打开。
```

如果没有 plugin 变更（仅 MCP 或 profile.json 更新），**省略**「需重启」提示。

---

## 注意事项

- `enabledPlugins` 是全局配置，修改会影响所有同时运行的 Claude Code 会话
- 备份文件保存在 `~/.claude/settings.json.bak.YYYYMMDD-HHMM`，自动保留最近 3 份
- 如需回滚，手动将备份文件复制回 `settings.json` 并重启 Claude Code
- 模板文件位于 `~/.claude/project-templates/`，可自由编辑自定义
