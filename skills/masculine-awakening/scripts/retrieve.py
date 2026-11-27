"""语义检索 → 取原文。对应最终方案的两个动作。

一、召回：用户问题向量化，跟预建的总结向量比对，取高分的几条。

    python scripts/retrieve.py "<问题>" --sem --list 5
        跨全部博主召回。只返回候选摘要（按相似度排序），交给模型判断哪条真能回答。

    python scripts/retrieve.py "<问题>" --sem --list 5 --blogger 潇洒哥
        只在这位博主的视频里召回。名字、别名、id 前缀都认。

    python scripts/retrieve.py "<问题>" --sem
        一步到位：过门槛的候选连完整口播稿一起返回。

二、取原文：模型判断完，按 id 取完整转写稿。

    python scripts/retrieve.py --pick <aweme_id,...>
        认完整 id，也认后 6 位短 id。跨博主取也能用，aweme_id 全局唯一。

没有 --sem 的旧关键词路径已经删除。检索只有这一条路，不存在两套逻辑漂移的问题。
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import semantic  # noqa: E402

BASE = Path(os.environ.get("KB_BASE") or Path(__file__).resolve().parent.parent)


def opt_path(rel, default=""):
    """可选文件的路径。空值返回 None 而不是 BASE 目录，
    否则后面 open() 一个目录会抛 PermissionError。"""
    rel = rel or default
    return BASE / rel if rel else None


def load_data():
    cfg = core.load_cfg()
    tpath = opt_path(cfg.get("transcript_file"), "data/transcripts.jsonl")
    transcripts = core.load_lines(tpath) if tpath and tpath.is_file() else []
    spath = opt_path(cfg.get("summary_file"), "data/summaries.json")
    summaries = core.load(spath) if spath and spath.is_file() else []
    return cfg, transcripts, summaries


def short_map(transcripts, summaries):
    """后 6 位短 id → 完整 aweme_id。模型看到短 id，回传时也只会给短 id。"""
    out = {}
    for row in list(transcripts) + list(summaries):
        vid = str(row.get("aweme_id") or "")
        if len(vid) >= 6:
            out[vid[-6:]] = vid
    return out


def resolve_ids(raw, smap):
    """短 id 还原成完整 id。认不出的原样返回，由下游报"取不到"。"""
    return [smap.get(x, x) for x in raw]


def fetch_text(vids, transcripts):
    """按 aweme_id 取完整口播稿。没有的就如实说没有，不拿别的凑。"""
    tmap = {str(t.get("aweme_id")): t for t in transcripts}
    out = []
    for vid in vids:
        t = tmap.get(vid)
        if t and t.get("text"):
            out.append({
                "aweme_id": vid,
                "blogger": t.get("blogger", ""),
                "blogger_id": t.get("blogger_id", ""),
                "title": t.get("title", ""),
                "publish_date": t.get("publish_date", ""),
                "duration": t.get("duration"),
                "chars": t.get("chars") or len(t.get("text", "")),
                "url": t.get("url", ""),
                "text": t.get("text", ""),
            })
        else:
            out.append({
                "aweme_id": vid,
                "missing_text": True,
                "chars": 0,
                "note": "这条视频的完整文案不在本包里（只建了向量，没转写全文）。",
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="用户的问题")
    ap.add_argument("--sem", action="store_true",
                    help="语义召回：问题向量化后与总结向量比对取高分")
    ap.add_argument("--blogger", default="",
                    help="只在这位博主的视频里找（认 id / 名字 / 别名）；不传则跨全部博主")
    ap.add_argument("--list", type=int, metavar="N",
                    help="只返回 N 条候选摘要，不取原文，交给模型判断")
    ap.add_argument("--pick", help="取原文：传 aweme_id 或后 6 位短 id，逗号分隔")
    ap.add_argument("--top", type=int, default=None,
                    help="召回几条候选，默认读 config 的 vector_top")
    ap.add_argument("--max-chars", type=int, default=8000, help="文案总字数预算，默认 8000")
    ap.add_argument("--backend", choices=["auto", "local", "api"], default="auto",
                    help="问题向量化的后端")
    ap.add_argument("--show-score", action="store_true", help="输出分数，标阈值用")
    args = ap.parse_args()

    try:
        cfg, transcripts, summaries = load_data()
    except FileNotFoundError:
        print(json.dumps({"hit": False, "answer": "本地知识库不完整"}, ensure_ascii=False))
        return

    # 取原文
    if args.pick:
        raw = [x.strip() for x in args.pick.split(",") if x.strip()]
        vids = resolve_ids(raw, short_map(transcripts, summaries))
        docs = fetch_text(vids, transcripts)
        total = sum(d["chars"] for d in docs)
        print(json.dumps({
            "hit": True,
            "picked": docs,
            "count": len(docs),
            "total_chars": total,
            "note": "text 是逐字转写稿，可能有同音错字。回答只能用这些文案里出现过的内容；"
                    "文案没提到的问题，直接说没讲到。每条都带 blogger 字段，"
                    "跨博主回答时必须标明这句是谁说的。",
        }, ensure_ascii=False))
        return

    if not args.question:
        print(json.dumps({"hit": False, "answer": "缺少问题参数"}, ensure_ascii=False))
        return

    if not args.sem:
        print(json.dumps({
            "hit": False, "reason": "missing_flag",
            "answer": "检索只有语义一条路，请加 --sem",
            "hint": 'python scripts/retrieve.py "<问题>" --sem --list 5',
        }, ensure_ascii=False))
        return

    top = args.top or args.list or cfg.get("vector_top", 3)
    try:
        r = semantic.search(
            args.question, top, None, None,
            False, args.backend, show=args.show_score, blogger=args.blogger,
        )
    except semantic.UnknownBlogger as e:
        print(json.dumps({
            "hit": False, "question": args.question, "reason": "unknown_blogger",
            "answer": str(e),
        }, ensure_ascii=False))
        return
    except semantic.NoEmbedder as e:
        print(json.dumps({
            "hit": False, "question": args.question, "reason": "no_embedder",
            "answer": str(e),
            "hint": "语义检索依赖 fastembed（pip install fastembed）；这不是可绕过的步骤。",
        }, ensure_ascii=False))
        return

    # 用户常常只丢一个词（「彩礼」「捞女」）。单词问法和总结的写法差异太大，
    # 分数容易卡在门槛下被判「没讲过」——实测「彩礼」0.5516 不中，补成「你怎么看彩礼」0.6307 就中。
    # 所以不中且问题很短时补一个问句重试一次，取更高的那次。
    if not r["hit"] and 0 < len(args.question.strip()) <= 8:
        alt = "你怎么看" + args.question.strip()
        r2 = semantic.search(alt, top, None, None, False, args.backend,
                             show=args.show_score, blogger=args.blogger)
        if r2["hit"] and r2.get("best_score", 0) > r.get("best_score", 0):
            r = r2
            r["rewritten_from"] = args.question
            r["question"] = args.question

    scope = r.get("scope")
    who = r.get("blogger") or ""

    if not r["hit"]:
        print(json.dumps({
            "hit": False, "question": args.question,
            "reason": r.get("reason"), "best_score": r["best_score"],
            "scope": scope, "blogger": who,
            "blocked_by": r.get("blocked_by"),
            "answer": ("「%s」没讲到这个问题" % who) if who else "这些博主都没讲到这个问题",
            "nearest": [{"score": c["score"], "blogger": c.get("blogger", ""),
                         "title": c["title"][:40]}
                        for c in (r.get("candidates") or [])],
        }, ensure_ascii=False))
        return

    # 只给候选摘要，判断权交给模型
    if args.list:
        print(json.dumps({
            "hit": True, "mode": "semantic_list", "question": args.question,
            "scope": scope, "blogger": who,
            "best_score": r["best_score"], "margin": r["margin"],
            "candidates": r["candidates"],
            "note": "这是向量召回的候选（按总结与本问题的相似度排序），不一定都对。"
                    "判断哪几条真能回答，再用 --pick <id,...> 取原文。"
                    "每条带 blogger 字段：指定博主提问时只用该博主的候选；"
                    "跨博主提问时每个候选都要标明是谁说的，不能混成一个人的观点。"
                    "如果最相关的也只是勉强沾边，就直说没讲到。",
        }, ensure_ascii=False))
        return

    # 一步到位：过门槛的才带原文
    # 向量分数整体偏集中（无关题也有 0.2~0.3），单靠绝对门槛会捎带无关视频，
    # 所以再加一道相对门槛：不能比第一名低太多。
    base = r["min_score"]
    floor = max(base, r["best_score"] * cfg.get("vector_ratio", 0.6))
    picked = [c for c in r["candidates"] if c["score"] >= floor]
    if not picked:
        print(json.dumps({
            "hit": False, "question": args.question, "reason": "below_floor",
            "best_score": r["best_score"], "floor": round(floor, 3),
            "scope": scope, "blogger": who,
            "answer": ("「%s」没讲到这个问题" % who) if who else "这些博主都没讲到这个问题",
        }, ensure_ascii=False))
        return

    docs, used = [], 0
    for c in picked:
        d = fetch_text([c["aweme_id"]], transcripts)[0]
        if docs and used + d["chars"] > args.max_chars:
            break
        d["score"] = c["score"]
        d["summary"] = c["summary"]
        if not d.get("blogger"):
            d["blogger"] = c.get("blogger", "")
        docs.append(d)
        used += d["chars"]

    print(json.dumps({
        "hit": True, "mode": "semantic", "question": args.question,
        "scope": scope, "blogger": who,
        "best_score": r["best_score"], "margin": r["margin"],
        "videos": docs, "returned": len(docs), "total_chars": used,
        "note": "videos[].text 是逐字转写稿，可能有同音错字。回答只能用这些文案里"
                "出现过的内容；候选里有沾边但没正面回答的，以原文为准，别替它补。"
                "跨博主时每条都要标出处（博主 + 日期 + 标题），不要把两个人的话揉成一段。",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
