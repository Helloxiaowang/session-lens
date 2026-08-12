#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sessions 索引脚本 —— 扫描 Claude Code + Codex 全部历史会话，输出统一索引。
HelloXW 出品，功能就仨：扫描、找、看大小。不删除任何东西，删你自己手动删。

用法（用 py 跑，本机 python 是 Store stub 会炸）：
  py scan.py                     # 默认列出最近 30 条会话
  py scan.py --top 100           # 列出最近 100 条
  py scan.py --find 关键词        # 按 项目/摘要 搜索
  py scan.py --platform codex     # 只看 codex
  py scan.py --sizes              # 按平台+项目 统计占用空间
  py scan.py record "干了啥"      # 手动给当前会话记一笔
  py scan.py --html               # 生成可视化网页（默认固定输出到 历史对话/session_index.html）
  py scan.py --html 其它.html     # 或指定其它输出路径
"""

import os
import sys
import re
import json
import glob
import argparse
from datetime import datetime, timezone, timedelta

# 扫描目录跟随用户主目录（开源通用，Windows/Linux/macOS 都行）
CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
CODEX_SESSIONS = os.path.expanduser("~/.codex/sessions")
RECORDS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "records.jsonl")
# 可视化网页固定输出路径（用户指定的目录），--html 不带参数就用它
DEFAULT_HTML = "F:/AI project/历史对话/session_index.html"

# 无意义消息黑名单：测活的、打招呼的、单字符的，拿来当摘要就是垃圾
MEANINGLESS = {
    "ping", "pong", "test", "测试", "在吗", "hello", "hi", "你好", "nihao",
    "123", "ok", "好的", "嗯", "0", "1", "a", "开始", "继续", ".",
    "。。。", "。。", "呵呵", "在", "嗯嗯", "收到", "谢谢", "好的好的",
}

# 截断长度
SUMMARY_LIMIT = 160
MSG_SAMPLE_LIMIT = 3


def clean_ws(s):
    """压缩多余空白，多行消息压成一行，方便表格展示"""
    return re.sub(r"\s+", " ", s or "").strip()


def is_meaningful(text):
    """判断一条用户消息值不值得当摘要。测活消息、slash命令、系统注入全部毙掉。"""
    t = clean_ws(text)
    if not t:
        return False
    if t.lower() in MEANINGLESS:
        return False
    if len(t) <= 2:  # 单字符/双字符基本没信息量
        return False
    # AGENTS.md 污染 / 系统注入
    if "# AGENTS.md" in t or "<INSTRUCTIONS>" in t or "<instructions>" in t:
        return False
    # Codex 环境上下文注入（session_meta 或 hook 塞的）
    if t.startswith("<environment_context>") or "<environment_context>" in t:
        return False
    # slash 命令及其回显（/model /clear /help 这类，Claude 会把回显也当用户消息）
    if t.startswith("/") or "<command-name>" in t or "<command-message>" in t or "<local-command-stdout>" in t:
        return False
    # 纯图片占位符（"[Image #1]" 这种，啥信息量都没有）
    if re.fullmatch(r"\[Image\s*#\d+\]", t):
        return False
    return True


def collect_body(text_parts):
    """把会话原始文本抽成可搜索正文：去重 + 过滤垃圾，\n\n 连接。详细模式全文搜索用。"""
    seen, parts = set(), []
    for m in text_parts:
        t = clean_ws(m)
        if not t or t in seen or not is_meaningful(t):
            continue
        seen.add(t)
        parts.append(t)
    return "\n\n".join(parts)


def pick_summary(msgs):
    """从一堆用户消息里挑出能代表这个会话干了啥的摘要。
    跳过 ping、slash命令、系统注入这类垃圾，取前几条有实质内容的拼接。"""
    meaningful = [m for m in msgs if is_meaningful(m)]
    if not meaningful:
        # 全是测活/垃圾消息，如实标注，别硬编个假摘要骗人
        return "(仅测试/无实质内容)"
    # 把 "[Image #1] xxx" 这种图片前缀剥掉，保留后面的文字
    cleaned = []
    for m in meaningful[:MSG_SAMPLE_LIMIT]:
        c = re.sub(r"^\[Image\s*#\d+\]\s*", "", clean_ws(m))
        cleaned.append(c)
    s = " | ".join(x for x in cleaned if x)
    return s[:SUMMARY_LIMIT]


def extract_text(content):
    """Claude 的 message.content 可能是字符串，也可能是对象数组，全给撸出来"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                if c.get("type") == "text" and c.get("text"):
                    parts.append(c["text"])
        return "\n".join(parts)
    return ""


def parse_ts(ts):
    """解析各种时间戳格式，解析失败返回 None"""
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def fmt_size(n):
    """字节数转人类可读"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ============================================================
# Codex 扫描
# ============================================================

def scan_codex():
    """扫 .codex/sessions/YYYY/MM/DD/rollout-*.jsonl"""
    sessions = []
    for path in glob.glob(os.path.join(CODEX_SESSIONS, "**", "rollout-*.jsonl"), recursive=True):
        try:
            size = os.path.getsize(path)
            meta = {}
            last_ts = None   # 文件最后一条带时间戳的行 = 最后一次活动时间
            event_msgs = []      # 干净的，event_msg 里的 user_message
            fallback_msgs = []   # response_item 里的 input_text（可能被污染）
            text_parts = []      # 全部正文素材（user+assistant），喂给 collect_body 抽可搜索正文
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    # 所有行都有 timestamp，按追加顺序最后一条就是最后活跃时间
                    ts = parse_ts(obj.get("timestamp"))
                    if ts:
                        last_ts = ts
                    t = obj.get("type")
                    if t == "session_meta":
                        meta = obj.get("payload", {})
                    elif t == "event_msg":
                        p = obj.get("payload", {})
                        if p.get("type") == "user_message":
                            m = p.get("message")
                            if m:
                                event_msgs.append(str(m))
                                text_parts.append(str(m))
                    elif t == "response_item":
                        p = obj.get("payload", {})
                        if p.get("type") == "message":
                            role = p.get("role")
                            for c in p.get("content") or []:
                                if isinstance(c, dict) and c.get("type") in ("input_text", "output_text") and c.get("text"):
                                    txt = str(c["text"])
                                    text_parts.append(txt)
                                    if role == "user":
                                        fallback_msgs.append(txt)
            # event 消息干净就用 event，否则退而求其次用 response_item
            user_msgs = event_msgs if event_msgs else fallback_msgs
            # 去掉重复（同一句可能同时出现在两个来源）
            seen, dedup = set(), []
            for m in user_msgs:
                key = clean_ws(m)
                if key and key not in seen:
                    seen.add(key)
                    dedup.append(m)
            summary = pick_summary(dedup)
            body = collect_body(text_parts)
            cwd = meta.get("cwd") or "?"
            sid = meta.get("session_id") or meta.get("id") or ""
            ts = last_ts  # 最后一次活动时间（文件最后一条带时间戳的行）
            sessions.append({
                "platform": "codex",
                "path": path,
                "size": size,
                "cwd": cwd,
                "sid": sid,
                "time": ts,
                "origin": meta.get("originator") or meta.get("cli_version") or "",
                "summary": summary,
                "body": body,
            })
        except Exception:
            continue
    return sessions


# ============================================================
# Claude Code 扫描
# ============================================================

def scan_claude():
    """扫 .claude/projects/<编码路径>/<uuid>.jsonl"""
    sessions = []
    if not os.path.isdir(CLAUDE_PROJECTS):
        return sessions
    for proj_dir in os.listdir(CLAUDE_PROJECTS):
        pdir = os.path.join(CLAUDE_PROJECTS, proj_dir)
        if not os.path.isdir(pdir):
            continue
        for fn in os.listdir(pdir):
            if not fn.endswith(".jsonl"):
                continue
            path = os.path.join(pdir, fn)
            try:
                size = os.path.getsize(path)
                cwd = None
                git_branch = None
                user_msgs = []
                text_parts = []  # 全部正文素材（user+assistant），喂给 collect_body 抽可搜索正文
                sid = None
                last_ts = None   # 文件最后一条带时间戳的行 = 最后一次活动时间
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        ts = parse_ts(obj.get("timestamp"))
                        if ts:
                            last_ts = ts
                        t = obj.get("type")
                        if t == "mode" and obj.get("sessionId"):
                            sid = obj.get("sessionId")
                        elif t == "user":
                            # 忽略 meta 注入的系统消息，只留真实用户输入
                            if obj.get("isMeta"):
                                continue
                            cwd = obj.get("cwd") or cwd
                            git_branch = obj.get("gitBranch") or git_branch
                            m = obj.get("message", {})
                            content = m.get("content") if isinstance(m, dict) else m
                            text = extract_text(content)
                            if text:
                                user_msgs.append(text)
                                text_parts.append(text)
                        elif t == "assistant":
                            # assistant 消息的文本块（详细模式全文搜索用）
                            m = obj.get("message", {})
                            content = m.get("content") if isinstance(m, dict) else m
                            text = extract_text(content)
                            if text:
                                text_parts.append(text)
                if not user_msgs:
                    continue
                summary = pick_summary(user_msgs)
                ts = last_ts  # 最后一次活动时间
                sessions.append({
                    "platform": "claude",
                    "path": path,
                    "size": size,
                    "cwd": cwd or proj_dir,
                    "sid": sid or fn[:-6],
                    "time": ts,
                    "origin": git_branch or "claude",
                    "summary": summary,
                    "body": collect_body(text_parts),
                })
            except Exception:
                continue
    return sessions


# ============================================================
# HTML 可视化输出（自包含单文件，双击即开）
# ============================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>会话索引 · Claude & Codex</title>
<style>
  :root{
    --bg:#0d1117; --card:#161b22; --card2:#1c2128; --line:#30363d;
    --fg:#e6edf3; --dim:#8b949e; --acc:#58a6ff; --cld:#8957e5; --cdx:#3fb950;
    --warn:#d29922; --mono:Consolas,'Courier New',monospace;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;padding:24px}
  .wrap{max-width:1400px;margin:0 auto}
  h1{font-size:22px;margin-bottom:4px}
  .sub{color:var(--dim);margin-bottom:20px;font-size:13px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .card .num{font-size:24px;font-weight:700;font-family:var(--mono)}
  .card .lbl{color:var(--dim);font-size:12px;margin-top:2px}
  .card .num.c{color:var(--cld)} .card .num.x{color:var(--cdx)}
  .bar{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:16px}
  .bar .lbl{color:var(--dim);font-size:12px;margin-bottom:8px}
  .bar-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
  .bar-row .nm{width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--dim);font-size:12px}
  .bar-row .trk{flex:1;height:8px;background:var(--card2);border-radius:4px;overflow:hidden}
  .bar-row .fl{height:100%;border-radius:4px;background:var(--acc)}
  .bar-row .sz{width:70px;text-align:right;font-family:var(--mono);font-size:12px}
  .toolbar{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap;align-items:center}
  input[type=search]{flex:1;min-width:220px;background:var(--card);border:1px solid var(--line);border-radius:8px;color:var(--fg);padding:8px 12px;font-size:14px;outline:none}
  input[type=search]:focus{border-color:var(--acc)}
  .btn{background:var(--card);border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:7px 14px;cursor:pointer;font-size:13px}
  .btn:hover{border-color:var(--acc)}
  .btn.on{background:var(--acc);border-color:var(--acc);color:#0d1117;font-weight:600}
  table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
  thead th{position:sticky;top:0;background:var(--card2);color:var(--dim);text-align:left;padding:10px 12px;font-size:12px;cursor:pointer;user-select:none;white-space:nowrap}
  thead th:hover{color:var(--fg)}
  thead th .arr{opacity:.5}
  tbody td{padding:9px 12px;border-top:1px solid var(--line);vertical-align:top;font-size:13px}
  tbody tr:hover{background:var(--card2)}
  .tag{display:inline-block;width:22px;text-align:center;border-radius:5px;font-family:var(--mono);font-weight:700;font-size:11px;padding:1px 0}
  .tag.c{background:rgba(137,87,229,.15);color:var(--cld)} .tag.x{background:rgba(63,185,80,.15);color:var(--cdx)}
  .cmd{font-family:var(--mono);font-size:12px;color:var(--fg);background:var(--card2);border:1px solid var(--line);border-radius:6px;padding:3px 8px;display:inline-block;cursor:pointer;white-space:nowrap;max-width:420px;overflow:hidden;text-overflow:ellipsis}
  .cmd:hover{border-color:var(--acc)}
  .copy{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:6px;padding:3px 8px;cursor:pointer;font-size:12px;margin-left:6px}
  .copy:hover{color:var(--fg);border-color:var(--acc)}
  .sum{max-width:480px}
  .path{font-family:var(--mono);font-size:11px;color:var(--dim);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
  .path:hover{color:var(--fg)}
  .empty{color:var(--dim);text-align:center;padding:40px;font-size:14px}
  .note{color:var(--warn)}
  .muted{color:var(--dim)}
  footer{color:var(--dim);font-size:12px;margin-top:20px;text-align:center}
  .rel{font-size:11px;color:var(--dim)}
  .badge-empty{color:var(--dim);font-style:italic}
  mark{background:var(--warn);color:#0d1117;border-radius:3px;padding:0 2px}
  .snip{margin-top:8px;border-left:2px solid var(--acc);padding-left:8px;display:flex;flex-direction:column;gap:4px}
  .snip-it{color:var(--dim);font-size:12px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
  .snip-it mark{background:var(--warn);color:#0d1117;border-radius:3px;padding:0 2px}
  .ops{width:76px;text-align:center;white-space:nowrap}
  .op{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:6px;padding:2px 7px;margin:0 2px;cursor:pointer;font-size:13px;line-height:1.4}
  .op:hover{border-color:var(--acc);color:var(--fg)}
  .op.del:hover{border-color:#f85149;color:#f85149}
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:100}
  .modal[hidden]{display:none}
  .modal-box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 22px;max-width:540px;width:92%;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  .modal-box h3{margin:0 0 10px;font-size:15px}
  .del-info{color:var(--dim);font-size:13px;line-height:1.6;word-break:break-all;margin-bottom:14px}
  .del-info .path{color:var(--acc);font-family:var(--mono);font-size:12px;white-space:normal;max-width:none}
  .modal-ops{display:flex;justify-content:flex-end;gap:8px}
  .btn.warn{background:#f85149;border-color:#f85149;color:#fff}
  .btn.warn:hover{border-color:#ff7b72}
  .cnt{margin-left:auto;color:var(--dim);font-size:12px;font-family:var(--mono);white-space:nowrap}
  .banner{display:flex;align-items:center;gap:8px;background:rgba(210,153,34,.12);border:1px solid rgba(210,153,34,.45);color:var(--warn);border-radius:8px;padding:8px 12px;font-size:13px;margin-bottom:14px;line-height:1.5}
  .banner[hidden]{display:none}
  .banner code{color:var(--fg);background:#0d1117;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-family:var(--mono)}
  .banner b{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <h1>💬 会话索引</h1>
  <div class="sub">__META__ · 点击命令/路径即可一键复制</div>

  <div class="cards">
    <div class="card"><div class="num" id="cTotal">0</div><div class="lbl">总会话</div></div>
    <div class="card"><div class="num" id="cSize">0</div><div class="lbl">总占用</div></div>
    <div class="card"><div class="num c" id="cClaude">0</div><div class="lbl">Claude Code</div></div>
    <div class="card"><div class="num x" id="cCodex">0</div><div class="lbl">Codex</div></div>
  </div>

  <div class="bar">
    <div class="lbl">磁盘占用 TOP（按项目）</div>
    <div id="sizeBars"></div>
  </div>

  <div class="banner" id="roBanner" hidden>🔌 当前是只读模式（file:// 打开）：『打开终端 / 删除』按钮不可用。
    请运行 <code>py -X utf8 scripts/server.py</code> 后访问 <b>http://localhost:8123/</b></div>

  <div class="toolbar">
    <input type="search" id="q" placeholder="🔍 关键词搜索，空格分隔多个词（如：星露谷 攻略）" autocomplete="off">
    <button class="btn on" data-f="all">全部</button>
    <button class="btn" data-f="claude">Claude</button>
    <button class="btn" data-f="codex">Codex</button>
    <button class="btn" data-f="empty">仅测试</button>
    <button class="btn deep" id="deepBtn" title="开启后搜索全部会话正文（不再只看摘要），命中时下方展示正文片段">🔍 详细模式</button>
    <span class="cnt" id="cnt"></span>
  </div>

  <table id="tbl">
    <thead>
      <tr>
        <th data-k="plat">平台</th>
        <th data-k="time">最后活动 <span class="arr">↕</span></th>
        <th data-k="cwd">项目目录</th>
        <th data-k="summary">主题 / 摘要</th>
        <th data-k="size">大小 <span class="arr">↕</span></th>
        <th>恢复命令</th>
        <th>完整路径</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <div class="empty" id="empty" style="display:none">没有匹配的会话</div>

  <footer>HelloXW 出品 · 起 <code>scripts/server.py</code> 后访问 http://localhost:8123/ 才能『打开终端 / 删除』，删除进回收站可恢复</footer>

  <div id="delModal" class="modal" hidden>
    <div class="modal-box">
      <h3>🗑 确认删除这个会话？</h3>
      <div class="del-info" id="delInfo"></div>
      <div class="modal-ops">
        <button class="btn" id="delCancel">取消</button>
        <button class="btn warn" id="delOk">删除（进回收站）</button>
      </div>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;
let cur=[], f='all', q='', sortK='time', sortAsc=false, deep=false;
let rowsCache=[]; // 操作按钮 data-idx -> session 对象（绝不把路径嵌进 HTML 属性，防引号转义坑）
const isHttp=location.protocol.startsWith('http'); // http 服务模式 vs file:// 静态模式
if(!isHttp)document.getElementById('roBanner').hidden=false; // file:// 只读模式：提示起服务

const fmtSize=n=>{for(const u of ['B','KB','MB','GB']){if(n<1024)return (u==='B'?n:n/1).toFixed(0)+u;n/=1024}return n.toFixed(1)+'TB'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rel=t=>{if(!t)return '';const d=(Date.now()-new Date(t))/864e5;if(d<1)return '今天';if(d<2)return '昨天';if(d<30)return Math.floor(d)+'天前';return Math.floor(d/30)+'月前'};

function copyText(t){
  if(navigator.clipboard){navigator.clipboard.writeText(t).then(()=>toast('已复制: '+t),()=>fallbackCopy(t));}
  else fallbackCopy(t);
}
function fallbackCopy(t){try{const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();const ok=document.execCommand('copy');ta.remove();toast('已复制'+(ok?'':'（可能未成功）')+': '+t);}catch(e){toast('复制失败，请手动选择: '+t);}}
function toast(msg){let t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.style.cssText='position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1c2128;border:1px solid var(--acc);color:var(--fg);padding:10px 18px;border-radius:8px;z-index:99;box-shadow:0 4px 20px rgba(0,0,0,.5)';document.body.appendChild(t);}t.textContent=msg;clearTimeout(t._h);t._h=setTimeout(()=>t.remove(),1800);}

// Everything 式搜索：把关键词加进搜索 haystack（含恢复命令），空格分隔多词 AND 匹配
function escRe(s){return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function hl(t){
  // t 已 esc 转义；把命中的关键词包成 <mark> 高亮
  if(!q)return t;
  for(const w of q.split(/\s+/)){
    if(!w)continue;
    try{t=t.replace(new RegExp(escRe(w),'gi'),m=>'<mark>'+m+'</mark>');}catch(e){}
  }
  return t;
}
function matchSession(x){
  if(!q)return true;
  // 详细模式开启时，搜索 haystack 加上会话全部正文（否则只看摘要/路径等）
  let hay=[x.platform,String(x.cwd),x.summary,String(x.path),x.sid,cmdOf(x)].join(' ').toLowerCase();
  if(deep&&x.body)hay+=' '+String(x.body).toLowerCase();
  return q.split(/\s+/).every(w=>hay.includes(w));
}

// 详细模式命中片段：从正文里挑最多 3 段含关键词的段落，截断后高亮展示
function snippetsOf(s){
  if(!deep||!q)return '';
  const body=String(s.body||'').toLowerCase();
  if(!body)return '';
  const words=q.split(/\s+/).filter(Boolean);
  if(!words.length)return '';
  const paras=String(s.body).split(/\n+/).filter(p=>p.trim());
  const hits=[];
  for(let i=0;i<paras.length&&hits.length<3;i++){
    if(words.some(w=>paras[i].toLowerCase().includes(w)))hits.push(paras[i]);
  }
  if(!hits.length)return '';
  // 截断时优先从第一个关键词位置附近取，保证关键词在片段内不被切掉
  const cut=p=>{
    if(p.length<=160)return p;
    const w=words.find(x=>p.toLowerCase().includes(x));
    if(!w)return p.slice(0,160)+'…';
    const i=p.toLowerCase().indexOf(w.toLowerCase());
    const start=Math.max(0,i-60);
    return (start>0?'…':'')+p.slice(start,start+160)+(start+160<p.length?'…':'');
  };
  return '<div class="snip">'+hits.map(p=>'<div class="snip-it">'+hl(esc(cut(p)))+'</div>').join('')+'</div>';
}

function platFilter(){return f==='all'?s=>true:s=>s.platform===(f==='empty'?'__never__':f);}
function apply(){
  let list=DATA.sessions.filter(platFilter());
  if(f==='empty')list=list.filter(x=>x.summary.includes('仅测试'));
  list=list.filter(matchSession);
  const sign=sortAsc?1:-1;
  list.sort((a,b)=>{
    if(sortK==='size')return (a.size-b.size)*sign;
    if(sortK==='time'){const ta=a.time?new Date(a.time):0,tb=b.time?new Date(b.time):0;return (ta-tb)*sign;}
    if(sortK==='cwd')return a.cwd.localeCompare(b.cwd)*sign;
    if(sortK==='plat')return a.platform.localeCompare(b.platform)*sign;
    if(sortK==='summary')return a.summary.localeCompare(b.summary)*sign;
    return 0;
  });
  cur=list;
  renderRows(list);
  renderStats();
  const cntEl=document.getElementById('cnt');
  if(cntEl)cntEl.textContent=q?`命中 ${list.length} / ${DATA.sessions.length} 条`:`${DATA.sessions.length} 条会话`;
}
function renderStats(){
  const all=DATA.sessions;
  document.getElementById('cTotal').textContent=all.length;
  document.getElementById('cSize').textContent=fmtSize(all.reduce((s,x)=>s+x.size,0));
  document.getElementById('cClaude').textContent=all.filter(x=>x.platform==='claude').length;
  document.getElementById('cCodex').textContent=all.filter(x=>x.platform==='codex').length;
}
function cmdOf(s){
  if(s.platform==='claude')return 'claude --resume '+s.sid;
  return s.sid ? 'codex resume '+s.sid : 'codex resume "'+s.path+'"';
}
function renderRows(list){
  const tb=document.getElementById('rows');tb.innerHTML='';
  rowsCache=[];
  document.getElementById('empty').style.display=list.length?'none':'block';
  for(const s of list){
    const idx=rowsCache.length;
    rowsCache.push(s);
    const tr=document.createElement('tr');
    const t=s.time?new Date(s.time):null;
    const tstr=t?`${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')} ${String(t.getHours()).padStart(2,'0')}:${String(t.getMinutes()).padStart(2,'0')}`:'--';
    const isEmpty=s.summary.includes('仅测试');
    const cmd=cmdOf(s);
    tr.innerHTML=`<td><span class="tag ${s.platform==='claude'?'c':'x'}">${s.platform==='claude'?'C':'X'}</span></td>`
      +`<td title="${esc(tstr)}">${esc(tstr)}<div class="rel">${esc(rel(s.time))}</div></td>`
      +`<td title="${esc(s.cwd)}">${hl(esc(s.cwd))}</td>`
      +`<td class="sum">${isEmpty?'<span class="badge-empty">'+hl(esc(s.summary))+'</span>':hl(esc(s.summary))}${snippetsOf(s)}</td>`
      +`<td style="font-family:var(--mono)">${fmtSize(s.size)}</td>`
      +`<td><span class="cmd" data-copy="${esc(cmd)}" title="点击复制">${esc(cmd)}</span></td>`
      +`<td><div class="path" data-copy="${esc(s.path)}" title="${esc(s.path)}">${hl(esc(s.path))}</div></td>`
      +`<td class="ops"><button class="op" data-act="open" data-idx="${idx}" title="在项目目录打开终端">📂</button><button class="op del" data-act="del" data-idx="${idx}" title="删除会话（进回收站）">🗑</button></td>`;
    tb.appendChild(tr);
  }
}
function renderBars(){
  const map={};
  for(const s of DATA.sessions)map[s.cwd]=(map[s.cwd]||0)+s.size;
  const arr=Object.entries(map).sort((a,b)=>b[1]-a[1]).slice(0,12);
  const max=arr.length?arr[0][1]:1;
  const el=document.getElementById('sizeBars');el.innerHTML='';
  for(const [nm,sz] of arr){
    const d=document.createElement('div');d.className='bar-row';
    d.innerHTML=`<div class="nm" title="${esc(nm)}">${esc(nm)}</div>`
      +`<div class="trk"><div class="fl" style="width:${(sz/max*100).toFixed(1)}%"></div></div>`
      +`<div class="sz">${fmtSize(sz)}</div>`;
    el.appendChild(d);
  }
}
document.getElementById('q').addEventListener('input',e=>{q=e.target.value.trim();apply();});
// 事件委托：点任何带 data-copy 的元素就复制，避开内联 onclick 的引号转义坑
document.addEventListener('click',e=>{const el=e.target.closest('[data-copy]');if(el)copyText(el.getAttribute('data-copy'));});
// 打开 / 删除按钮：http 服务模式走后端 API；file:// 静态模式降级为复制命令
function doOpen(s){
  if(!s.cwd){toast('该会话没有项目目录');return;}
  if(isHttp){
    fetch('/api/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:s.cwd})})
      .then(r=>r.json()).then(j=>toast(j.msg)).catch(()=>toast('请求失败：服务没起？'));
  }else{
    // file:// 下浏览器不能弹终端，降级为复制进入目录的命令，起服务后才是真打开
    copyText('cd /d "'+s.cwd+'"');
    toast('只读模式：已复制进入该目录的命令（起服务后可一键打开终端）');
  }
}
let pendingDel=null;
function delCmd(s){
  // 静态模式降级：生成进回收站的 PowerShell 命令，复制给用户自己跑
  const p=String(s.path).replace(/'/g,"''");
  return "powershell -NoProfile -Command \"Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('"+p+"', 'OnlyErrorDialogs', 'SendToRecycleBin')\"";
}
function doDel(s){
  if(!s.path){toast('没有可删除的会话文件');return;}
  if(isHttp){
    pendingDel=s;
    document.getElementById('delInfo').innerHTML=
      '<div><span class="tag '+(s.platform==='claude'?'c':'x')+'">'+(s.platform==='claude'?'C':'X')+'</span> '+esc(s.summary||'(无摘要)')+'</div>'
      +'<div class="path">'+esc(s.path)+'</div>'
      +'<div class="rel">'+fmtSize(s.size)+' · '+esc(rel(s.time)||'--')+'</div>';
    document.getElementById('delModal').hidden=false;
  }else{
    copyText(delCmd(s));
    toast('已复制删除命令，粘贴到终端执行（进回收站）');
  }
}
// 操作按钮事件委托（data-idx -> rowsCache，不内联路径，防属性转义坑）
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-act]');
  if(!b)return;
  const s=rowsCache[+b.dataset.idx];
  if(!s)return;
  if(b.dataset.act==='open')doOpen(s);
  else if(b.dataset.act==='del')doDel(s);
});
document.getElementById('delCancel').addEventListener('click',()=>{pendingDel=null;document.getElementById('delModal').hidden=true;});
document.getElementById('delOk').addEventListener('click',()=>{
  const s=pendingDel;pendingDel=null;
  document.getElementById('delModal').hidden=true;
  if(!s)return;
  fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:s.path})})
    .then(r=>r.json()).then(j=>{
      if(j.ok){DATA.sessions=DATA.sessions.filter(x=>x!==s);apply();toast(j.msg);}
      else toast(j.msg);
    }).catch(()=>toast('请求失败：服务没起？'));
});
document.getElementById('delModal').addEventListener('click',e=>{
  if(e.target.id==='delModal'){pendingDel=null;document.getElementById('delModal').hidden=true;}
});
document.querySelectorAll('.toolbar .btn:not(.deep)').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.toolbar .btn:not(.deep)').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');f=b.dataset.f;apply();
}));
// 详细模式开关：切换后重新过滤+渲染，开启时按钮高亮
document.getElementById('deepBtn').addEventListener('click',()=>{
  deep=!deep;
  document.getElementById('deepBtn').classList.toggle('on',deep);
  apply();
});
document.querySelectorAll('thead th').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k;if(!k)return;
  if(sortK===k)sortAsc=!sortAsc;else{sortK=k;sortAsc=false;}
  apply();
}));
renderBars();
apply();
</script>
</body>
</html>
"""


def build_html(sessions, out_path):
    """生成自包含 HTML 索引页。数据内嵌，双击就能看，不用起服务。"""
    records = []
    if os.path.isfile(RECORDS_FILE):
        try:
            with open(RECORDS_FILE, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass
    data = []
    for s in sessions:
        data.append({
            "platform": s["platform"],
            "path": s["path"].replace("\\", "/"),
            "size": s["size"],
            "cwd": s["cwd"],
            "sid": s["sid"],
            "time": s["time"].isoformat() if s["time"] else None,
            "summary": s["summary"],
            "body": s.get("body", ""),
        })
    total = sum(x["size"] for x in data)
    import datetime as _dt
    meta = ("生成于 " + _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + f" · 共 {len(data)} 条会话 · {fmt_size(total)}"
            + (f" · {len(records)} 条手动记录" if records else ""))
    payload = {"sessions": data, "records": records}
    # 内嵌 JSON 必须把 < 转成 <，否则正文里出现 </script> 会提前截断 script 标签
    html = (HTML_TEMPLATE
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"))
            .replace("__META__", esc_html(meta)))
    os.makedirs(os.path.dirname(out_path), exist_ok=True) if os.path.dirname(out_path) else None
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"HTML 已生成: {out_path}")
    print(f"双击打开即可查看。想重新生成就跑: py scan.py --html")


def esc_html(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))




def sort_sessions(sessions):
    """时间降序，没时间的放最后"""
    def key(s):
        t = s["time"]
        return t.timestamp() if t else 0
    return sorted(sessions, key=key, reverse=True)


def print_index(sessions, top):
    """打印人类可读的会话索引表"""
    sessions = sort_sessions(sessions)[:top]
    print(f"共 {len(sessions)} 条会话（按时间倒序）\n")
    for i, s in enumerate(sessions, 1):
        t = s["time"].strftime("%m-%d %H:%M") if s["time"] else "??-?? ??"
        icon = "C" if s["platform"] == "claude" else "X"
        cwd = s["cwd"]
        # 路径太长截断
        if len(cwd) > 38:
            cwd = "..." + cwd[-35:]
        print(f"[{i:>3}] {t} {icon} {fmt_size(s['size']):>6}  {cwd:<38}  {s['summary']}")
    print("")
    print("C=Claude Code  X=Codex   cwd=项目目录  size=会话占用磁盘")
    print("恢复: Claude `claude --resume <sid>` | Codex `codex resume` 或直接粘贴上面的 jsonl 路径")


def print_sizes(sessions):
    """按 平台 -> 项目 统计磁盘占用，帮你找出吃硬盘的大户"""
    totals = {}
    for s in sessions:
        key = (s["platform"], s["cwd"])
        totals.setdefault(key, 0)
        totals[key] += s["size"]
    total_all = sum(v for _, v in totals.items())
    print(f"总占用: {fmt_size(total_all)}  ({len(sessions)} 个会话文件)\n")
    order = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    for (plat, cwd), size in order:
        print(f"{fmt_size(size):>8}  [{plat}]  {cwd}")
    # 平台汇总
    print("")
    plat_total = {}
    for s in sessions:
        plat_total[s["platform"]] = plat_total.get(s["platform"], 0) + s["size"]
    for plat, size in sorted(plat_total.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{fmt_size(size):>8}  平台汇总 [{plat}]")


def find_sessions(sessions, kw):
    """在 cwd 和摘要里模糊搜索"""
    kw_low = kw.lower()
    hits = []
    for s in sessions:
        if kw_low in s["cwd"].lower() or kw_low in s["summary"].lower() or kw_low in os.path.basename(s["path"]).lower():
            hits.append(s)
    return hits


def record_entry(text):
    """手动给当前会话记一笔，追加到 records.jsonl。
    这样即使没开 skill 记录，也能在索引里看到手动备注。"""
    os.makedirs(os.path.dirname(RECORDS_FILE), exist_ok=True)
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": text,
    }
    with open(RECORDS_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"已记录: {entry['ts']}  {text}")


def show_records():
    """列出所有手动记录"""
    if not os.path.isfile(RECORDS_FILE):
        print("还没有手动记录。用 `py scan.py record \"干了啥\"` 记一笔。")
        return
    with open(RECORDS_FILE, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                print(f"{e.get('ts','')}  {e.get('note','')}")
            except Exception:
                continue


def main():
    parser = argparse.ArgumentParser(description="会话索引扫描器")
    parser.add_argument("--top", type=int, default=30, help="列出最近 N 条 (默认 30)")
    parser.add_argument("--find", help="按关键词搜索项目/摘要")
    parser.add_argument("--platform", choices=["claude", "codex"], help="只看某个平台")
    parser.add_argument("--sizes", action="store_true", help="统计磁盘占用")
    parser.add_argument("--records", action="store_true", help="查看手动记录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--html", nargs="?", const=DEFAULT_HTML, metavar="OUT", help="生成可视化 HTML 网页（不带路径用默认 F:/AI project/历史对话/session_index.html）")
    parser.add_argument("cmd", nargs="?", default="index", help="index | record")
    parser.add_argument("arg", nargs="?", help="record 的内容")
    args = parser.parse_args()

    if args.cmd == "record":
        if not args.arg:
            print("record 需要一个内容参数，比如: py scan.py record \"今天修了登录的bug\"")
            sys.exit(1)
        record_entry(args.arg)
        return

    if args.records:
        show_records()
        return

    sessions = []
    if args.platform in (None, "claude"):
        sessions += scan_claude()
    if args.platform in (None, "codex"):
        sessions += scan_codex()

    if args.json:
        out = [{"platform": s["platform"], "path": s["path"], "size": s["size"],
                "cwd": s["cwd"], "sid": s["sid"], "summary": s["summary"],
                "time": s["time"].isoformat() if s["time"] else None} for s in sessions]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.find:
        hits = find_sessions(sessions, args.find)
        if not hits:
            print(f"没找到包含 \"{args.find}\" 的会话")
            return
        print(f"搜索 \"{args.find}\" 命中 {len(hits)} 条:\n")
        print_index(hits, len(hits))
    elif args.sizes:
        print_sizes(sessions)
    elif args.html:
        build_html(sessions, args.html or DEFAULT_HTML)
    else:
        print_index(sessions, args.top)


if __name__ == "__main__":
    main()
