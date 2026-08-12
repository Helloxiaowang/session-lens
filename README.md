# session-lens- · 会话透镜

**跨平台会话索引器** —— 把 Claude Code 和 Codex 的所有历史会话，扫进一个可搜索的 HTML 面板。
解决换 API 平台后 `/resume` 找不到记录、忘了哪个项目聊过什么、忘了清理占内存会话的问题。

> HelloXW 出品 · 双击 `dist/SessionLens.exe` 一条龙（重扫 + 起服务 + 开浏览器），『打开终端 / 删除』按钮可用，删除进回收站可恢复

## 功能

- **跨平台扫描**：Claude Code（`~/.claude/projects`）+ Codex（`~/.codex/sessions`）一次扫全
- **可视化网页**：自包含单 HTML，双击即开。统计卡片 + 磁盘占用 TOP12 + 可排序表格 + 一键复制恢复命令
- **Everything 式搜索**：多关键词空格分隔 AND 匹配，命中词高亮，实时显示"命中 N / 总条"
- **🔍 详细模式**：在全部会话正文里搜（不只摘要），命中行展开含关键词的正文片段
- **📂 打开 / 🗑 删除按钮**：每行操作列，起本地服务后在项目目录打开命令窗口 / 删除会话（进回收站）；file:// 双击打开为只读模式，按钮降级为复制命令
- **只读不删**：默认只统计不删除，删除是用户主动操作且进回收站可恢复（防止误删）

## 一键 exe（不用记命令）

不想记"先 `scan.py --html` 再 `server.py` 再手动开浏览器"那一堆？直接双击 `dist/SessionLens.exe`：

- **首次双击**：自动重扫 Claude + Codex 全部会话 → 起本地服务（127.0.0.1:8123）→ 自动弹出浏览器索引页
- **再双击**：检测到服务已在跑，只打开浏览器，不重复起服务
- **弹出的控制台窗口 = 服务开关**：关闭窗口即停止服务
- exe 模式下网页『📂 打开终端 / 🗑 删除』按钮直接可用（删除进回收站可恢复）

本地自己打包（需要 Python + PyInstaller）：

```bash
py -m pip install pyinstaller
cd 本仓库根目录
py -m PyInstaller --onefile --name SessionLens --paths scripts launcher.py
```

产物 `dist/SessionLens.exe`（约 9MB，单文件免依赖，拷哪都能跑）。
开发/调试直接跑源码：`py -X utf8 launcher.py`（行为跟 exe 一模一样）。

## 安装

把它当作 Claude Code Skill 放进全局技能目录：

```bash
git clone git@github.com:Helloxiaowang/session-lens-.git ~/.claude/skills/sessions/
```

对话里说 `/sessions`（或提"会话 / 聊天记录 / 恢复会话"等）即可触发。

> 脚本用 `py` 跑（本机 `python` 可能是 Microsoft Store stub 会 exit 49）：
> `py -X utf8 "路径/scripts/scan.py"`

## 用法

```bash
py scan.py                    # 列出最近 30 条会话
py scan.py --top 100          # 列出最近 100 条
py scan.py --find 关键词       # 按 项目/摘要 搜索
py scan.py --platform codex    # 只看 Codex（或 --platform claude）
py scan.py --sizes             # 按 平台→项目 统计磁盘占用
py scan.py record "干了啥"     # 手动给当前会话记一笔
py scan.py --html              # 生成可视化网页
py scan.py --html 其它路径.html # 生成到指定路径
py scripts/server.py           # 起本地服务（默认 8123），让网页『打开/删除』按钮真生效
```

## 可视化网页

`py scan.py --html` 生成自包含单 HTML（`__DATA__` 内嵌会话数据），双击浏览器即开：

- 统计卡片：总会话数 / 总磁盘占用 / Claude 数 / Codex 数
- 磁盘占用 TOP12 条形图（按项目）
- 可排序表格：平台 / 最后活动 / 项目目录 / 摘要 / 大小 / **恢复命令** / 完整路径 / **操作**
- **Everything 式搜索**：空格分隔多词 AND 匹配（如 `星露谷 攻略`），命中词 `<mark>` 高亮
- **恢复命令一键复制**：Claude 用 `claude --resume <sid>`，Codex 用 `codex resume <sid>`
- **🔍 详细模式**：默认只看摘要；开启后搜全部会话正文，命中行展开含关键词的正文片段（最多 3 段，从关键词位置居中截取，同样高亮）
- **📂 打开 / 🗑 删除**：file:// 双击打开是**只读模式**——页面顶部出现橙色提示条，打开按钮降级为复制 `cd /d "目录"` 命令、删除按钮降级为复制回收站命令；起 `scripts/server.py` 后访问 `http://localhost:8123/`，打开按钮在**项目目录下打开命令窗口**（优先 Windows Terminal，兜底 cmd），删除按钮弹确认框后真删（进回收站可恢复）

默认输出到 `F:/AI project/历史对话/session_index.html`（脚本顶部 `DEFAULT_HTML` 常量可改，用 Windows 绝对路径）。

## 本地服务（server.py）

网页的『打开/删除』按钮在纯 file:// 下浏览器限制不能操作本地文件，起服务后生效：
- **📂 打开** → `POST /api/open`，在**项目目录下打开命令窗口**（优先 Windows Terminal，兜底 cmd 新控制台）——方便直接敲 `claude --resume` 恢复对话
- **🗑 删除** → `POST /api/delete`，弹确认框后把会话文件删进回收站

```bash
py scripts/server.py    # 默认端口 8123，浏览器访问 http://localhost:8123/
```

安全设计：只监听 `127.0.0.1`；删除白名单 = `~/.claude/projects` 和 `~/.codex/sessions` 下的 `.jsonl`（realpath 前缀校验，防任意路径删除）；删除走 Windows 回收站（PowerShell Microsoft.VisualBasic，零第三方依赖）。

## 关键设计

- **最后活动时间** = 文件最后一条带 `timestamp` 字段的行（追加顺序），比 session_meta 的 timestamp 更准
- **摘要过滤**：`ping` 测活、slash 命令回显、`<environment_context>`、AGENTS.md 注入、纯图片占位符全部剔除，抓前几条有实质内容的用户消息
- **复制功能**用 `data-copy` 属性 + document 事件委托（内联 onclick 嵌 JSON 会踩引号转义坑）
- **操作按钮**不把路径嵌进 HTML 属性，用 `data-idx` 索引 → `rowsCache` 数组映射 session 对象，删除走确认 modal + 成功后即时刷新

## 相关

- 状态：可用 ✅ · 默认只统计不删除，删除进回收站可恢复 · MIT License
