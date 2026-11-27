"""读原文：列博主、列目录、看全文、按关键词找原话。仅用标准库。

和 retrieve.py 的分工：
- retrieve.py --sem   找哪条视频能回答问题（向量召回）
- retrieve.py --pick  取已知 id 的视频口播稿
- read.py             浏览式查阅：不知道 id 时先列博主 / 列目录 / 按关键词定位

用法：
    python scripts/read.py                              # 列出收录的博主
    python scripts/read.py --list                       # 列出全部文案目录
    python scripts/read.py --list --blogger 潇洒哥        # 只看这位博主的
    python scripts/read.py --id 7636681187343691697     # 读全文
    python scripts/read.py --search "孝心外包"           # 找原话出现在哪几条
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

BASE = Path(os.environ.get("KB_BASE") or Path(__file__).resolve().parent.parent)


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def filter_by_blogger(rows, key, bloggers):
    """按博主过滤。key 为空返回原行；认不出就报错退出，不要静默返回全部。"""
    if not key:
        return rows
    target, err = core.match_blogger(key, bloggers)
    if err:
        print(err)
        sys.exit(1)
    want = str(target.get("id") or "")
    out = [r for r in rows if str(r.get("blogger_id") or "") == want]
    if not out:
        print("「%s」没有全文数据" % target.get("name"))
        sys.exit(1)
    return out


def show_bloggers(rows, bloggers):
    if not bloggers:
        print("包里没有博主清单")
        return
    print("收录 %d 位博主：\n" % len(bloggers))
    for b in bloggers:
        bid = str(b.get("id") or "")
        mine = [r for r in rows if str(r.get("blogger_id") or "") == bid]
        c = b.get("counts") or {}
        chars = int(c.get("chars") or sum(int(r.get("chars") or 0) for r in mine))
        aliases = "、".join(b.get("aliases") or []) or "-"
        print("%s（%s）" % (b.get("name", "?"), bid or "-"))
        print("  别名：%s" % aliases)
        print("  %d 条有口播（全文库 %d 条）· %d 字 · %s"
              % (int(c.get("speech") or len(mine)), len(mine), chars,
                 c.get("range", "-")))
        if c.get("silent"):
            print("  其中 %d 条无口播（纯 BGM 或转写失败），不参与检索" % c["silent"])
        print()
    print("看某位的全部文案：python scripts/read.py --list --blogger <名字>")
    print("读全文：python scripts/read.py --id <aweme_id>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bloggers", action="store_true", help="列出收录的博主")
    ap.add_argument("--list", action="store_true", help="列出文案目录")
    ap.add_argument("--blogger", default="", help="限定博主（名字 / 别名 / id）")
    ap.add_argument("--id", help="按 aweme_id 读全文")
    ap.add_argument("--search", help="关键词检索原文")
    ap.add_argument("--context", type=int, default=40, help="命中处前后各取多少字")
    ap.add_argument("--limit", type=int, default=0, help="限制 --search 返回条数")
    args = ap.parse_args()

    cfg = json.load(open(BASE / "config.json", encoding="utf-8"))
    rel = cfg.get("transcript_file", "data/transcripts.jsonl")
    path = BASE / rel
    if not path.exists():
        print("全文库缺失：" + rel + "，请重新安装技能包")
        sys.exit(1)

    rows = load(path)
    bloggers = core.load_bloggers(cfg)

    # 没有任何参数时，先让人看见有哪些博主
    if not (args.list or args.id or args.search or args.bloggers):
        show_bloggers(rows, bloggers)
        return

    if args.bloggers:
        show_bloggers(rows, bloggers)
        return

    rows = filter_by_blogger(rows, args.blogger, bloggers)
    who = args.blogger.strip()

    if args.id:
        hit = [r for r in rows if str(r["aweme_id"]) == str(args.id)]
        if not hit:
            print("没有这条：" + args.id)
            sys.exit(1)
        r = hit[0]
        print(r.get("blogger", "") + " | " + r["publish_date"] + " | "
              + str(r.get("duration")) + "s | " + str(r["chars"]) + "字")
        print("标题：" + r["title"])
        print("链接：" + r["url"])
        print()
        print(r["text"])
        return

    if args.search:
        kw = args.search
        found = []
        for r in rows:
            text = r["text"]
            pos = text.find(kw)
            if pos < 0:
                continue
            s = max(0, pos - args.context)
            e = min(len(text), pos + len(kw) + args.context)
            found.append((r, text[s:e]))
        if not found:
            print(("这位博主的" if who else "全部") + "文案里没有出现「" + kw + "」，可以换同义词再试")
            return
        if args.limit:
            found = found[: args.limit]
        print("「" + kw + "」出现在 " + str(len(found)) + " 条文案里：\n")
        for r, snip in found:
            print((r.get("blogger", "") + " | " if r.get("blogger") else "")
                  + r["publish_date"] + " | " + r["title"])
            print("  ..." + snip + "...")
            print("  " + r["url"] + "\n")
        return

    total = sum(r["chars"] for r in rows)
    print("共 " + str(len(rows)) + " 条文案，" + str(total) + " 字\n")
    for i, r in enumerate(rows, 1):
        print(str(i) + ". " + (r.get("blogger", "") + " | " if r.get("blogger") else "")
              + r["publish_date"] + " | " + str(r["chars"]) + "字 | "
              + str(r.get("duration")) + "s | " + r["aweme_id"])
        print("   " + r["title"])
    print("\n读全文：python scripts/read.py --id <aweme_id>")


if __name__ == "__main__":
    main()
