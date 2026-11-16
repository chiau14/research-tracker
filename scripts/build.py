#!/usr/bin/env python3
"""讀取 TODO.md、logs/、experiments/，產生靜態網頁到 docs/。

規則見 CLAUDE.md。只使用 Python 標準庫。
用法：python3 scripts/build.py
"""
import html
import re
import shutil
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "docs"

# 導覽列：(輸出檔名, 顯示名稱)。新增頁面類型時在這裡加一項（CLAUDE.md 第 9 節）。
NAV = [
    ("index.html", "首頁"),
    ("timeline.html", "時間線"),
    ("experiments.html", "實驗表"),
    ("todo.html", "待辦"),
]

STATUSES = {"planned": "規劃中", "running": "進行中", "done": "完成", "failed": "失敗"}
LOG_FIELDS = {"date": True, "tags": False}  # 欄位: 是否必填
EXP_FIELDS = {"id": True, "title": True, "status": True, "date": True, "commit": False}
TODO_SECTIONS = ["進行中", "待做", "已完成"]

SENSITIVE = [
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "IP 位址"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "email"),
    (re.compile(r"/home/|/Users/|[A-Z]:\\"), "本機路徑"),
    (re.compile(r"\bsk-[A-Za-z0-9]{8,}"), "API key"),
    (re.compile(r"\.(?:ckpt|pt|pth|safetensors)\b"), "checkpoint 檔"),
]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

errors = []


def error(path, msg):
    errors.append(f"[錯誤] {path.relative_to(ROOT)}: {msg}")


def warn(path, msg):
    print(f"[警告] {path.relative_to(ROOT)}: {msg}")


# ---------- 讀取與檢查 ----------

def check_sensitive(path, text):
    for n, line in enumerate(text.splitlines(), 1):
        for pattern, label in SENSITIVE:
            if pattern.search(line):
                error(path, f"第 {n} 行疑似含有{label}，請移除後再建置")


def parse_front_matter(path, fields):
    """回傳 (meta, body)。只支援 `key: value` 與 `key: [a, b]`。"""
    text = path.read_text(encoding="utf-8")
    check_sensitive(path, text)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        error(path, "缺少開頭的 front matter（第一行必須是 ---）")
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        error(path, "front matter 沒有結尾的 ---")
        return {}, text
    meta = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            error(path, f"front matter 格式錯誤：{line!r}")
            continue
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        meta[key] = value
    for key, required in fields.items():
        if required and not meta.get(key):
            error(path, f"缺少必填欄位 {key}")
    for key in meta:
        if key not in fields:
            warn(path, f"未知欄位 {key}（已忽略）")
    return meta, "\n".join(lines[end + 1:])


def load_logs():
    logs = []
    for path in sorted((ROOT / "logs").glob("*.md")):
        meta, body = parse_front_matter(path, LOG_FIELDS)
        if not DATE_RE.match(path.stem):
            error(path, "檔名必須是 YYYY-MM-DD.md")
        elif meta.get("date") and meta["date"] != path.stem:
            error(path, f"date 欄位 {meta['date']} 與檔名不一致")
        tags = meta.get("tags", [])
        logs.append({"date": path.stem, "tags": tags if isinstance(tags, list) else [tags], "body": body})
    return sorted(logs, key=lambda x: x["date"], reverse=True)


def load_experiments():
    exps = []
    for path in sorted((ROOT / "experiments").glob("*.md")):
        meta, body = parse_front_matter(path, EXP_FIELDS)
        if not re.match(r"^exp-\d{3}$", path.stem):
            error(path, "檔名必須是 exp-NNN.md（三位數）")
        if meta.get("id") and meta["id"] != path.stem:
            error(path, f"id 欄位 {meta['id']} 與檔名不一致")
        if meta.get("status") and meta["status"] not in STATUSES:
            error(path, f"status 必須是 {' / '.join(STATUSES)} 之一")
        if meta.get("date") and not DATE_RE.match(meta["date"]):
            error(path, "date 必須是 YYYY-MM-DD")
        exps.append({**meta, "id": path.stem, "body": body})
    return exps


def load_todo():
    path = ROOT / "TODO.md"
    text = path.read_text(encoding="utf-8")
    check_sensitive(path, text)
    sections = {name: [] for name in TODO_SECTIONS}
    current = None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            current = line[3:].strip()
            if current not in sections:
                error(path, f"第 {n} 行：未知區塊「{current}」，只能是 {'、'.join(TODO_SECTIONS)}")
                current = None
            continue
        m = re.match(r"^- \[( |x)\] (.+)$", line)
        if not m or current is None:
            continue
        done, rest = m.group(1) == "x", m.group(2)
        date = re.search(r"@(\d{4}-\d{2}-\d{2})", rest)
        if done and not date:
            error(path, f"第 {n} 行：已完成項目必須有 @YYYY-MM-DD")
        sections[current].append({"done": done, "text": rest})
    return sections


# ---------- Markdown 轉 HTML（只支援 CLAUDE.md 第 5 節列出的語法） ----------

def inline(text, root):
    codes = []

    def keep_code(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"#(exp-\d{3})\b", rf'<a href="{root}exp/\1.html">\1</a>', text)
    text = re.sub(r"@(\d{4}-\d{2}-\d{2})", r'<span class="muted">✓ \1</span>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def md_to_html(text, root="", shift=0):
    out, para, items = [], [], []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para), root)}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items.clear()

    lines = iter(text.splitlines())
    for line in lines:
        if line.startswith("```"):
            flush()
            code = []
            for inner in lines:
                if inner.startswith("```"):
                    break
                code.append(inner)
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        elif m := re.match(r"^(#{2,3}) (.+)$", line):
            flush()
            level = min(len(m.group(1)) + shift, 6)
            out.append(f"<h{level}>{inline(m.group(2), root)}</h{level}>")
        elif m := re.match(r"^- \[( |x)\] (.+)$", line):
            para and flush()
            box = "☑" if m.group(1) == "x" else "☐"
            items.append(f'<li class="task">{box} {inline(m.group(2), root)}</li>')
        elif line.startswith("- "):
            para and flush()
            items.append(f"<li>{inline(line[2:], root)}</li>")
        elif not line.strip():
            flush()
        else:
            items and flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


# ---------- 輸出頁面 ----------

BASE = Template((SCRIPTS / "templates" / "base.html").read_text(encoding="utf-8"))


def write_page(rel, title, content):
    depth = rel.count("/")
    root = "../" * depth
    current = rel if depth == 0 else {"exp": "experiments.html"}.get(rel.split("/")[0])
    nav = " ".join(
        f'<a href="{root}{href}"' + (' aria-current="page"' if href == current else "") + f">{name}</a>"
        for href, name in NAV
    )
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BASE.substitute(title=html.escape(title), root=root, nav=nav, content=content), encoding="utf-8")


def status_badge(status):
    return f'<span class="status status-{status}">{STATUSES.get(status, status)}</span>'


def tags_html(tags):
    return '<p class="tags">' + "".join(f"<span>{html.escape(t)}</span>" for t in tags) + "</p>" if tags else ""


def todo_list(items, root=""):
    if not items:
        return '<p class="muted">無</p>'
    return md_to_html("\n".join(f"- [{'x' if i['done'] else ' '}] {i['text']}" for i in items), root)


def build_index(logs, exps, todo):
    parts = []
    if logs:
        latest = logs[0]
        parts.append(f'<h2>最新進度：{latest["date"]}</h2><div class="card">{tags_html(latest["tags"])}'
                     f'{md_to_html(latest["body"], shift=1)}</div>')
    parts.append("<h2>進行中</h2>" + todo_list(todo["進行中"]))
    parts.append("<h2>待做</h2>" + todo_list(todo["待做"]))
    stats = "".join(
        f'<li><strong>{sum(e.get("status") == s for e in exps)}</strong>{status_badge(s)}</li>' for s in STATUSES
    )
    parts.append(f'<h2>實驗狀態</h2><ul class="stats">{stats}</ul><p><a href="experiments.html">查看所有實驗 →</a></p>')
    write_page("index.html", "首頁", "\n".join(parts))


def build_timeline(logs):
    parts = [f'<p class="muted">共 {len(logs)} 份日誌，新到舊排列。</p>']
    for log in logs:
        parts.append(f'<article class="card" id="{log["date"]}"><h2>{log["date"]}</h2>'
                     f'{tags_html(log["tags"])}{md_to_html(log["body"], shift=1)}</article>')
    write_page("timeline.html", "時間線", "\n".join(parts))


def build_experiments(exps):
    buttons = '<button type="button" data-filter="all" aria-pressed="true">全部</button>' + "".join(
        f'<button type="button" data-filter="{s}" aria-pressed="false">{label}</button>' for s, label in STATUSES.items()
    )
    rows = "".join(
        f'<tr data-status="{e.get("status", "")}"><td><a href="exp/{e["id"]}.html">{e["id"]}</a></td>'
        f'<td>{html.escape(e.get("title", ""))}</td><td>{status_badge(e.get("status", ""))}</td>'
        f'<td>{e.get("date", "")}</td></tr>'
        for e in exps
    )
    content = (f'<div class="filters" hidden>{buttons}</div>'
               f'<table><thead><tr><th>編號</th><th>標題</th><th>狀態</th><th>日期</th></tr></thead>'
               f'<tbody>{rows}</tbody></table>')
    write_page("experiments.html", "實驗表", content)
    for e in exps:
        commit = f' · commit <code>{html.escape(e["commit"])}</code>' if e.get("commit") else ""
        head = f'<p>{status_badge(e.get("status", ""))} <span class="muted">{e["id"]} · {e.get("date", "")}{commit}</span></p>'
        write_page(f'exp/{e["id"]}.html', e.get("title", e["id"]), head + md_to_html(e["body"], root="../"))


def build_todo(todo):
    content = "".join(f"<h2>{name}</h2>{todo_list(items)}" for name, items in todo.items())
    write_page("todo.html", "待辦", content)


# ---------- 連結檢查 ----------

def check_links():
    broken = []
    for page in sorted(OUT.rglob("*.html")):
        for target in re.findall(r'(?:href|src)="([^"#]+)', page.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target):
                continue  # 外部連結不檢查
            if not (page.parent / target).resolve().exists():
                broken.append(f"[錯誤] 斷掉的連結：{page.relative_to(ROOT)} → {target}")
    return broken


def main():
    logs, exps, todo = load_logs(), load_experiments(), load_todo()
    if errors:
        print("\n".join(errors))
        print(f"\n建置中止：{len(errors)} 個錯誤。docs/ 未更動。")
        return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(SCRIPTS / "static", OUT / "assets")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    build_index(logs, exps, todo)
    build_timeline(logs)
    build_experiments(exps)
    build_todo(todo)
    broken = check_links()
    if broken:
        print("\n".join(broken))
        return 1
    pages = len(list(OUT.rglob("*.html")))
    print(f"建置完成：{pages} 個頁面，{len(logs)} 份日誌，{len(exps)} 個實驗。連結檢查通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
