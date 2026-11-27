"""通用 IO 与博主索引。只有标准库，零依赖。

这个文件原来还负责分词、关键词打分、原子匹配（v1 的关键词检索方案）。
那套在 2026-11-26 全部删掉了——检索现在只有一条路：semantic.py 的总结向量。

2026-11-27 起一个包装多位博主，所以这里多了一件事：读博主清单、按名字/别名定位博主。
"""
import json
import os
from pathlib import Path

BASE = Path(os.environ.get("KB_BASE") or Path(__file__).resolve().parent.parent)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_lines(path):
    """读 jsonl"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_cfg():
    return load(BASE / "config.json")


def bloggers_path(cfg=None):
    cfg = cfg or load_cfg()
    return BASE / (cfg.get("bloggers_file") or "data/bloggers.json")


def load_bloggers(cfg=None):
    """博主清单。老格式（单博主、没有 bloggers.json）自动降级成一条。"""
    p = bloggers_path(cfg)
    if p.is_file():
        rows = load(p)
        if isinstance(rows, dict):
            rows = rows.get("bloggers") or []
        return rows
    cfg = cfg or load_cfg()
    kb = cfg.get("kb") or {}
    name = kb.get("blogger")
    if not name:
        return []
    return [{"id": kb.get("creator_id") or "", "name": name,
             "aliases": kb.get("aliases") or []}]


def blogger_map(rows):
    """id → 清单条目，检索结果里标博主名用。"""
    return {str(b.get("id") or ""): b for b in rows}


def _names(b):
    out = {str(b.get("name") or ""), str(b.get("raw_nickname") or "")}
    for a in (b.get("aliases") or []):
        out.add(str(a))
    out.discard("")
    return out


def match_blogger(key, rows=None):
    """按 id / id 前缀 / 名字 / 别名定位一位博主。

    返回 (条目, 错误信息)。命中时错误为 None；找不到或对上多个都返回错误。
    """
    rows = load_bloggers() if rows is None else rows
    key = (key or "").strip()
    if not key:
        return None, "没指定博主"
    if not rows:
        return None, "这个包里没有博主清单（data/bloggers.json 缺失）"

    for b in rows:
        if str(b.get("id") or "") == key:
            return b, None

    low = key.lower()
    pref = [b for b in rows if str(b.get("id") or "").lower().startswith(low)]
    if len(pref) == 1:
        return pref[0], None

    named = [b for b in rows if key in _names(b)]
    if len(named) == 1:
        return named[0], None
    if len(named) > 1:
        return None, "「%s」对上多位博主：%s，请说全名" % (
            key, "、".join(str(b.get("name")) for b in named))

    loose = [b for b in rows if any(key in n for n in _names(b))]
    if len(loose) == 1:
        return loose[0], None

    return None, "没有这位博主：「%s」。已收录的是：%s" % (
        key, "、".join(str(b.get("name")) for b in rows))
