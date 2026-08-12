#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话索引网页的本地服务：让『打开项目目录』『删除会话』按钮真正生效。

纯 file:// 双击打开网页时，JS 受浏览器限制不能操作本地文件，删除按钮只能降级
为复制命令。启动本服务后浏览器访问 http://localhost:8123 打开网页，两个按钮
走后端 API 真生效。

用法:
    py -X utf8 server.py [端口]     # 默认 8123，Ctrl+C 停止

API:
    POST /api/open    {"path": "项目目录"}   用资源管理器打开该目录
    POST /api/delete  {"path": "会话文件"}   删除会话文件（进回收站，可恢复）

安全设计:
    - 只监听 127.0.0.1，只有本机能访问
    - 删除只允许 ~/.claude/projects 和 ~/.codex/sessions 下的 .jsonl（白名单校验，
      防任意路径删除）
    - 删除进回收站（PowerShell + Microsoft.VisualBasic，零第三方依赖），可恢复
"""
import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# 网页输出目录（跟 scan.py --html 无参默认路径一致）
HTML_DIR = "F:/AI project/历史对话"
# 删除白名单：只允许删这两个目录下的会话文件
ALLOW_ROOTS = [
    os.path.join(os.path.expanduser("~"), ".claude", "projects"),
    os.path.join(os.path.expanduser("~"), ".codex", "sessions"),
]


def in_allow_roots(path):
    """校验路径在白名单根目录内，防任意文件删除。"""
    rp = os.path.realpath(path)
    for root in ALLOW_ROOTS:
        rr = os.path.realpath(root)
        if rp == rr or rp.startswith(rr + os.sep):
            return True
    return False


def send_to_recycle_bin(path):
    """Windows 删除进回收站：PowerShell 调 Microsoft.VisualBasic，零第三方依赖。"""
    esc = str(path).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
        "'%s', 'OnlyErrorDialogs', 'SendToRecycleBin')" % esc
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True, capture_output=True, text=True,
    )


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kw):
        super().__init__(*args, directory=HTML_DIR, **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _send(self, ok, msg):
        body = json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # 根路径直接进网页，别让用户看到目录列表
        if self.path in ("", "/"):
            self.send_response(302)
            self.send_header("Location", "/session_index.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        data = self._read_json()
        if self.path == "/api/open":
            p = data.get("path", "")
            if not p or not os.path.isdir(p):
                self._send(False, "目录不存在: " + p)
                return
            try:
                os.startfile(p)  # Windows 资源管理器打开项目目录
                self._send(True, "已打开: " + p)
            except Exception as e:
                self._send(False, "打开失败: %s" % e)
        elif self.path == "/api/delete":
            p = data.get("path", "")
            if not p or not os.path.isfile(p) or not p.endswith(".jsonl"):
                self._send(False, "只允许删除会话 .jsonl 文件")
                return
            if not in_allow_roots(p):
                self._send(False, "拒绝删除：只能删 Claude/Codex 会话文件")
                return
            try:
                send_to_recycle_bin(p)
                self._send(True, "已删除（进回收站，可恢复）")
            except Exception as e:
                self._send(False, "删除失败: %s" % e)
        else:
            self._send(False, "未知接口: " + self.path)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    os.makedirs(HTML_DIR, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("会话索引服务已启动: http://localhost:%d/" % port)
    print("网页里『打开/删除』按钮走本服务生效；Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
