#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SessionLens 一键启动器：双击就完事。

把会话索引做成 exe 后，用户不需要再记"先跑 scan.py --html，再起 server.py，
再手动开浏览器"那一堆命令。双击本 exe：

  1. 检测 8123 端口 —— 服务已经在跑就直接打开浏览器退出，不重复起服务
  2. 没在跑 → 重新扫描 Claude + Codex 全部会话，生成最新 HTML 索引页
  3. 起本地服务（127.0.0.1:8123）→ 自动打开浏览器
  4. 保持前台运行：这个控制台窗口就是服务的"开关"，关掉窗口服务即停

打包：PyInstaller --onefile --name SessionLens --paths scripts launcher.py
开发模式直接跑：py -X utf8 launcher.py
"""
import os
import sys
import socket
import webbrowser

# scripts 目录塞进搜索路径：开发模式跑源码时能找到 scan/server 两个模块。
# 打包成 exe 后模块已内嵌，scripts 目录不存在，这行自动跳过。
_BASE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_BASE, "scripts")
if os.path.isdir(_SCRIPTS):
    sys.path.insert(0, _SCRIPTS)

import scan
import server

PORT = 8123
URL = "http://localhost:%d/" % PORT


def _service_running():
    """试连 8123，通 = 服务已在本机跑着。"""
    s = socket.socket()
    try:
        s.settimeout(1)
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    # 控制台中文输出稳一点（exe 里 stdout 编码不确定，直接按 UTF-8 来）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if _service_running():
        print("服务已在运行，直接打开浏览器: " + URL)
        webbrowser.open(URL)
        return

    print("正在扫描 Claude + Codex 全部会话…")
    sessions = scan.scan_claude() + scan.scan_codex()
    scan.build_html(sessions, scan.DEFAULT_HTML)

    os.makedirs(server.HTML_DIR, exist_ok=True)
    srv = server.ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    print("")
    print("会话索引服务已启动: " + URL)
    print("「打开终端 / 删除」按钮已可用，删除进回收站可恢复。")
    print("关闭本窗口即停止服务。")
    webbrowser.open(URL)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
