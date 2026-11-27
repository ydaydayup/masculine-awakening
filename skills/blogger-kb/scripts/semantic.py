"""语义检索：问题向量化 → 与预建的总结向量比对 → 取高分。

这是主路径，取代关键词粗筛。文档侧向量由创作者预建随包分发（data/vectors.npy），
用户端只需要把问题编码成同一空间的向量，一次矩阵乘法出结果。

用法：
    python scripts/semantic.py "儿媳有没有义务孝顺公婆"
    python scripts/semantic.py "怎么减肥最快"                # 会拒答
    python scripts/semantic.py "问题" --top 5 --show-score    # 看分数分布，调阈值用

输出 JSON，字段与 retrieve.py 对齐，便于同一套调用代码两种模式切换。

两个门槛（重要）：
    min_score   绝对下限。最高分不到这里，判定为「没讲过」，直接拒答。
    min_margin  第一名与第二名的差距。默认只做提示，不否决——
                因为「多条都相关」时 margin 天然很小，用它硬拒会误伤。
                需要严格拒答时加 --strict。

阈值必须用你自己的全量数据来标，不要用别人的默认值。
标法：把 20~30 个已知该答的问题和 10 个已知该拒的问题各跑一遍 --show-score，
看两类分数的重叠带，门槛放在重叠带中间。
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

BASE = Path(os.environ.get("KB_BASE") or Path(__file__).resolve().parent.parent)


class NoEmbedder(Exception):
    pass


class UnknownBlogger(Exception):
    pass


def load_index(cfg=None):
    cfg = cfg or core.load_cfg()
    vrel = cfg.get("vector_file") or "data/vectors.npy"
    mrel = cfg.get("vector_meta") or "data/vectors.json"
    vpath, mpath = BASE / vrel, BASE / mrel
    if not vpath.is_file() or not mpath.is_file():
        raise FileNotFoundError("向量库不存在，先跑 tools/build_vectors.py")
    meta = json.load(open(mpath, encoding="utf-8"))
    mat = np.load(vpath).astype(np.float32)
    if mat.shape[0] != len(meta["ids"]):
        raise ValueError("向量行数与 ids 数量不一致，请重建向量库")
    return mat, meta


def scope_block(question, best, cfg):
    """话题外黑名单，只对擦边分生效。

    向量衡量「语义有多近」，不衡量「他到底讲没讲过」。实测最典型的一条：
    「婆婆不给我带孩子怎么办」拿 0.547，比最弱的命中题 0.467 还高——
    因为婆媳、责任确实是他常年讲的话题，只是没讲过带孩子这件事。

    所以黑名单不能当硬否决（会误杀以后真的讲了的内容），
    只在分数还没高到「明显命中」时才用它把擦边题拦掉。
    分数超过 min_score × ceiling 就不再拦，交给模型判断。
    """
    hits = [w for w in (cfg.get("out_of_scope") or []) if w and w in question]
    if not hits:
        return None
    ceiling = cfg.get("vector_min_score", 0.45) * cfg.get("vector_scope_ceiling", 1.4)
    return hits if best < ceiling else None


def encode_query(text, model_name, backend, prefix):
    """把问题编码成向量。失败时抛 NoEmbedder，由上层给出可执行的提示。"""
    if backend in ("auto", "local"):
        try:
            from fastembed import TextEmbedding
        except ImportError:
            if backend == "local":
                raise NoEmbedder("没装 fastembed，执行：pip install fastembed")
        else:
            model = TextEmbedding(model_name=model_name)
            v = list(model.query_embed([prefix + text]))[0]
            return np.asarray(v, dtype=np.float32)

    base, key = os.getenv("EMBED_API_BASE"), os.getenv("EMBED_API_KEY")
    if base and key:
        import urllib.request
        req = urllib.request.Request(
            base.rstrip("/") + "/embeddings",
            data=json.dumps({"model": model_name, "input": [prefix + text]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return np.asarray(data["data"][0]["embedding"], dtype=np.float32)

    raise NoEmbedder("没有可用的 embedding 后端：装 fastembed（pip install fastembed），"
                     "或设置 EMBED_API_BASE / EMBED_API_KEY")


def resolve_scope(blogger, meta, bloggers):
    """把 --blogger 解析成一组行号。返回 (命中条目, 行号数组)。

    不传 blogger 时返回 (None, None) 表示全库检索。
    """
    if not blogger:
        return None, None
    target, err = core.match_blogger(blogger, bloggers)
    if err:
        raise UnknownBlogger(err)

    bmeta = meta.get("blogger_ids") or []
    if not bmeta:
        # 老格式的包只有一位博主，整库都是他
        return target, np.arange(len(meta["ids"]), dtype=int)

    want = str(target.get("id") or "")
    idx = np.array([i for i, b in enumerate(bmeta) if str(b) == want], dtype=int)
    if idx.size == 0:
        raise UnknownBlogger("「%s」在向量库里没有数据，可能只入了清单没建向量"
                             % target.get("name"))
    return target, idx


def search(question, top=3, min_score=None, min_margin=None, strict=False,
           backend="auto", show=False, blogger=None):
    """语义召回。blogger 为空时跨全部博主，给定时只在该博主的视频里比。"""
    cfg = core.load_cfg()
    mat, meta = load_index(cfg)
    bloggers = core.load_bloggers(cfg)
    target, allowed = resolve_scope(blogger, meta, bloggers)
    bmap = core.blogger_map(bloggers)

    # 阈值：显式传参 > 该博主自己标定的 > 全局默认
    if min_score is None:
        if target is not None and target.get("min_score") is not None:
            min_score = float(target["min_score"])
        else:
            min_score = float(cfg.get("vector_min_score", 0.45))
    if min_margin is None:
        min_margin = float(cfg.get("vector_min_margin", 0.02))

    q = encode_query(question, meta["model"], backend, meta.get("query_prefix", ""))
    if q.shape[0] != mat.shape[1]:
        raise ValueError("问题向量 %d 维，索引 %d 维，模型不一致：索引用的 %s"
                         % (q.shape[0], mat.shape[1], meta["model"]))

    q = q / (np.linalg.norm(q) + 1e-9)
    sims = mat @ q
    if allowed is not None:
        masked = np.full(sims.shape, -1.0, dtype=np.float32)
        masked[allowed] = sims[allowed]
        sims = masked
    n_valid = int(allowed.size) if allowed is not None else int(sims.shape[0])

    order = np.argsort(-sims)
    best = float(sims[order[0]])
    second = float(sims[order[1]]) if n_valid > 1 else 0.0
    margin = best - second

    summaries = {}
    srel = cfg.get("summary_file") or "data/summaries.json"
    spath = BASE / srel
    if spath.is_file():
        for s in json.load(open(spath, encoding="utf-8")):
            summaries[str(s["aweme_id"])] = s

    bmeta = meta.get("blogger_ids") or []

    # 候选行号。跨博主时必须按博主分组各取几条——
    # 否则内容多的博主会把 top 全占满，内容少的永远露不出来，
    # 「大家怎么看」就变成了「那位话最多的怎么看」。
    picks = None
    if allowed is None and len(bloggers) > 1 and bmeta:
        quota = max(1, -(-top // len(bloggers)))
        chosen = []
        for b in bloggers:
            bid = str(b.get("id") or "")
            idx = [i for i, x in enumerate(bmeta) if str(x) == bid]
            if not idx:
                continue
            sub = sims[idx]
            lo = b.get("min_score")
            lo = float(lo) if lo is not None else float(cfg.get("vector_min_score", 0.45))
            for j in np.argsort(-sub)[:quota]:
                if float(sub[j]) >= lo:
                    chosen.append(int(idx[j]))
        if chosen:
            picks = sorted(set(chosen), key=lambda i: -sims[i])[:top]
    if picks is None:
        picks = [int(i) for i in order[: min(top, n_valid)]]

    rows = []
    for k in picks:
        vid = str(meta["ids"][k])
        s = summaries.get(vid, {})
        bid = str(bmeta[k]) if bmeta else str(s.get("blogger_id") or "")
        row = {
            "aweme_id": vid,
            "score": round(float(sims[k]), 4),
            "title": s.get("title", ""),
            "publish_date": s.get("publish_date", ""),
            "chars": s.get("chars", 0),
            "summary": s.get("summary", ""),
            "topics": s.get("topics", []),
            "url": s.get("url", ""),
        }
        if bid:
            row["blogger_id"] = bid
            row["blogger"] = bmap.get(bid, {}).get("name") or s.get("blogger") or bid
        rows.append(row)

    reason = ""
    blocked = None
    if best < min_score:
        reason = "below_score"
    elif strict and margin < min_margin:
        reason = "low_margin"
    else:
        blocked = scope_block(question, best, cfg)
        if blocked:
            reason = "out_of_scope"

    out = {
        "hit": not reason,
        "question": question,
        "best_score": round(best, 4),
        "margin": round(margin, 4),
        "min_score": min_score,
        "min_margin": min_margin,
        "scope": "blogger" if target is not None else "all",
        "index_size": n_valid,
        "model": meta["model"],
    }
    if target is not None:
        out["blogger"] = target.get("name")
        out["blogger_id"] = target.get("id")
    if blocked:
        out["blocked_by"] = blocked
    if reason:
        out["reason"] = reason
        out["answer"] = ("「%s」没讲到这个问题" % target.get("name")) if target \
            else "这些博主都没讲到这个问题"
        out["candidates"] = rows[:3] if show else []
    else:
        out["candidates"] = rows
    if show:
        out["note"] = ("best_score 是最高余弦；margin 是第一名减第二名。"
                       "调阈值就看这两个数。")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--top", type=int, default=3, help="返回几条候选，默认 3")
    ap.add_argument("--blogger", default="", help="只在这位博主的视频里找；不传则跨全部博主")
    ap.add_argument("--min-score", type=float, default=None,
                    help="绝对下限，不传则读该博主标定值或 config 的 vector_min_score")
    ap.add_argument("--min-margin", type=float, default=None,
                    help="第一二名最小差距，仅 --strict 时生效")
    ap.add_argument("--strict", action="store_true", help="margin 不够也拒答（多条都相关时会误伤）")
    ap.add_argument("--backend", choices=["auto", "local", "api"], default="auto")
    ap.add_argument("--show-score", action="store_true", help="输出分数字段，标阈值用")
    args = ap.parse_args()

    try:
        out = search(args.question, args.top, args.min_score, args.min_margin,
                     args.strict, args.backend, args.show_score, args.blogger)
    except UnknownBlogger as e:
        out = {"hit": False, "reason": "unknown_blogger", "answer": str(e)}
    except NoEmbedder as e:
        out = {"hit": False, "reason": "no_embedder", "answer": str(e),
               "hint": "装不了本地模型时，退回全量标签路径：retrieve.py --labels"}
    except FileNotFoundError as e:
        out = {"hit": False, "reason": "no_index", "answer": str(e)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

