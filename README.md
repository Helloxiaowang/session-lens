# session-lens- · 会话透镜

**跨平台会话索引器** —— 把 Claude Code 和 Codex 的所有历史会话，扫进一个可搜索的 HTML 面板。
解决换 API 平台后 `/resume` 找不到记录、忘了哪个项目聊过什么、忘了清理占内存会话的问题。

> HelloXW 出品 · 只统计不删除 · 手动删会话自己动手

## 功能

- **跨平台扫描**：Claude Code（`~/.claude/projects`）+ Codex（`~/.codex/sessions`）一次扫全
- **可视化网页**：自包含单 HTML，双击即开。统计卡片 + 磁盘占用 TOP12 + 可排序表格 + 一键复制恢复命令
- **Everything 式搜索**：多关键词空格分隔 AND 匹配，命中词高亮，实时显示"命中 N / 总条"
- **只读不删**：只统计不删除任何文件，删会话你自己动手（防止误删）

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
```

## 可视化网页

`py scan.py --html` 生成自包含单 HTML（`__DATA__` 内嵌会话数据），双击浏览器即开：

- 统计卡片：总会话数 / 总磁盘占用 / Claude 数 / Codex 数
- 磁盘占用 TOP12 条形图（按项目）
- 可排序表格：平台 / 最后活动 / 项目目录 / 摘要 / 大小 / **恢复命令** / 完整路径
- **Everything 式搜索**：空格分隔多词 AND 匹配（如 `星露谷 攻略`），命中词 `<mark>` 高亮
- **恢复命令一键复制**：Claude 用 `claude --resume <sid>`，Codex 用 `codex resume <sid>`

默认输出到 `F:/AI project/历史对话/session_index.html`（脚本顶部 `DEFAULT_HTML` 常量可改，用 Windows 绝对路径）。

## 关键设计

- **最后活动时间** = 文件最后一条带 `timestamp` 字段的行（追加顺序），比 session_meta 的 timestamp 更准
- **摘要过滤**：`ping` 测活、slash 命令回显、`<environment_context>`、AGENTS.md 注入、纯图片占位符全部剔除，抓前几条有实质内容的用户消息
- **复制功能**用 `data-copy` 属性 + document 事件委托（内联 onclick 嵌 JSON 会踩引号转义坑）

## 相关

- 状态：可用 ✅ · 只统计不删除 · MIT License
