---
name: sessions
description: >
  跨平台会话索引器。扫描 Claude Code 和 Codex 的全部历史会话，展示每个会话的
  项目目录(cwd)、发生时间、磁盘占用和"干了啥"摘要。解决你换 API 平台后 /resume
  找不到记录、忘了哪个进程/项目在跑、忘了清理占内存会话的问题。
  触发方式：用户说"sessions""会话""聊天记录""找不到会话""恢复会话""resume"
  "看看有什么会话""清理会话""哪个会话占空间""我忘了上次在哪聊了""查一下记录"
  "哪个项目聊过什么" 等；或直接 `/sessions`。
user_invocable: true
---

# Sessions 跨平台会话索引器

把 Claude Code（`~/.claude/projects`）和 Codex（`~/.codex/sessions`）的所有历史会话扫一遍，
输出统一索引：**项目目录 + 平台 + 时间 + 磁盘占用 + 内容摘要**。
只读、不删除任何文件。删除会话请用户自己手动删（防止误删，HelloXW 不背锅）。

## 怎么跑

脚本在 `scripts/scan.py`，**必须用 `py` 跑**（本机 `python` 是 Store stub 会炸）。

```bash
py "C:/Users/w3346/.claude/skills/sessions/scripts/scan.py"
```

## 命令一览

| 命令 | 作用 |
|------|------|
| `scan.py` | 列出最近 30 条会话（时间倒序） |
| `scan.py --top 100` | 列出最近 100 条 |
| `scan.py --find 关键词` | 按 项目目录/摘要/文件名 搜索，如 `--find 星露谷` |
| `scan.py --platform codex` | 只看 Codex（或 `--platform claude`） |
| `scan.py --sizes` | 按 平台→项目 统计磁盘占用，找吃硬盘大户 |
| `scan.py --records` | 看手动记录 |
| `scan.py record "干了啥"` | 手动给当前会话记一笔（写进 records.jsonl） |
| `scan.py --json` | 输出 JSON，方便其他工具处理 |
| `scan.py --html` | 生成**自包含可视化网页**（单 html，双击即开，可一键复制恢复命令）。**无参默认固定输出到 `F:/AI project/历史对话/session_index.html`**，目录自动创建 |
| `scan.py --html 其它路径.html` | 指定其它输出路径 |

## 可视化网页（--html）

用户想要"看得清的索引"时，跑：

```bash
py -X utf8 "C:/Users/w3346/.claude/skills/sessions/scripts/scan.py" --html
```

> 不带参数默认输出到 `F:/AI project/历史对话/session_index.html`（目录自动创建）；
> `--html 其它路径.html` 可指定其它输出位置。

网页特性：
- 单文件自包含，`__DATA__` 占位符内嵌会话 JSON + `__META__` 生成信息，双击浏览器即开，无依赖。
- 统计卡片：总会话数 / 总磁盘占用 / Claude 数 / Codex 数。
- 磁盘占用 TOP12 条形图（按项目）。
- 表格列：平台 / 最后活动 / 项目目录 / 主题摘要 / 大小 / **恢复命令** / 路径。
- **恢复命令可点击一键复制**（`data-copy` 属性 + document 事件委托，别改回内联 onclick——双引号转义坑）。
- 筛选按钮：全部 / Claude / Codex / 仅测试；顶部搜索框 = **Everything 式关键词搜索**：
  空格分隔多词 AND 匹配（例：`星露谷 攻略`），命中字段含 平台/cwd/摘要/路径/sid/恢复命令，
  命中词黄色 `<mark>` 高亮，工具栏右侧显示"命中 N / 52 条"；表头可排序。
- **🔍 详细模式开关**（工具栏右侧）：默认**只看摘要**；点开后在**全部会话正文**里搜
  （不只摘要），命中行摘要下方展开**含关键词的正文片段**（最多 3 段，每段优先从关键词
  位置居中截取 ≤160 字符，关键词同样 `<mark>` 高亮）。搜摘要里没有的词（如正文独有细节）
  时用它，关掉就和原来一模一样。

恢复会话 = 复制网页里那行"恢复命令"到终端跑：
- Claude Code: `claude --resume <sid>`
- Codex: `codex resume <sid>`（无 sid 时退化为 `codex resume "<完整路径>"`）

## 在对话里怎么用

用户想看会话时，按下面来：

1. **先跑 `--top` 列最近会话**，把表格直接原样贴给用户（别自己精简，用户要看全）。
2. 用户说"帮我找 xxx" → 跑 `--find xxx`。
3. 用户说"哪个占空间大" → 跑 `--sizes`。
4. 用户想标记当前会话 → 跑 `record`，问清楚摘要内容后写入：
   ```bash
   py "C:/Users/w3346/.claude/skills/sessions/scripts/scan.py" record "<用户说的内容>"
   ```
5. 用户问"怎么恢复某个会话" → 看表格里那行的平台，告诉用户：
   - **Claude Code**: `claude --resume <会话编号或 sid>`（本机一般用 `claude -r` 选）
   - **Codex**: `codex resume`（带 `--last` 直接恢复最近一个），或直接粘贴索引里的 jsonl 完整路径
6. 用户想清理某会话 → **只读，不删**。先 `--sizes` 告诉用户哪个项目占了多少，
   再给删除建议但让用户自己动手（文件路径已在表格/JSON 里）。

## 关键细节（别改坏）

- 摘要过滤：`ping`、`测试`、`/model` 这类 slash 命令回显、`<environment_context>`、
  AGENTS.md 注入、纯图片占位符都会跳过，不会污染摘要。抓的是**前几条有实质内容的用户消息**。
- 磁盘占用按单个 jsonl 文件大小统计，反映的是会话占的真实硬盘空间。
- 跨平台靠 cwd 字段（Claude 的 user 消息、Codex 的 session_meta 都带）定位项目。
- **最后活动时间 = 文件最后一条带 `timestamp` 字段的行**（追加顺序），比 session_meta 的 timestamp 更准。
  网页/表格里的"最后活动"就是它。
- 不要改脚本的路径常量（写死了 Windows 路径），本机就是 Windows。
- 生成网页别用内联 onclick 嵌 JSON——双引号直接进 HTML 属性会截断。
  统一用 `data-copy` + document 事件委托。
- **详细模式会内嵌全部正文**（`body` 字段）进 `__DATA__`，HTML 会到几 MB 属正常。
  内嵌 JSON 必须 `.replace("<", "\\u003c")`——否则正文里出现 `</script>` 会提前截断 script 标签。
- `matchSession` 里 haystack 变量要用 `let`（详细模式开启时 `hay += body`），`const` 会重赋值报错。
