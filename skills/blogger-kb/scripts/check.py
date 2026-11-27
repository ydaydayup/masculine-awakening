"""校验知识库完整性（多博主版）。仅用标准库。

包里是四位一体的数据：总结、全文、向量矩阵、向量元数据，外加一份博主清单。
任何一份缺失、数量对不上、博主归属错乱，检索都会静默出错——不报错，只是悄悄答错人。
所以第一次使用前必须先跑这个。

用法：
    python scripts/check.py
输出：
    第一行 ok / missing 主结论，后面按博主列明细。
"""
import json
import os
import sys
from pathlib import Path

BASE = Path(os.environ.get("KB_BASE") or Path(__file__).resolve().parent.parent)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg_path = BASE / "config.json"
    if not cfg_path.exists():
        print("missing config.json")
        sys.exit(1)
    cfg = load(cfg_path)

    required = [cfg.get("summary_file"), cfg.get("transcript_file"),
                cfg.get("vector_file"), cfg.get("vector_meta"),
                cfg.get("bloggers_file")]
    required = [r for r in required if r]
    missing = [r for r in required
               if not (BASE / r).is_file() or (BASE / r).stat().st_size == 0]
    if missing:
        print("missing " + ", ".join(missing))
        if any("vector" in m for m in missing):
            print("提示：跑 template/tools/build_vectors.py 生成向量库")
        sys.exit(1)

    bloggers = load(BASE / cfg["bloggers_file"])
    if isinstance(bloggers, dict):
        bloggers = bloggers.get("bloggers") or []
    if not bloggers:
        print("missing 博主清单为空：%s" % cfg["bloggers_file"])
        sys.exit(1)
    bmap = {str(b.get("id") or ""): b for b in bloggers}

    summaries = load(BASE / cfg["summary_file"])
    transcripts = []
    with open(BASE / cfg["transcript_file"], encoding="utf-8") as f:
        for line in f:
            if line.strip():
                transcripts.append(json.loads(line))

    problems = []

    # 1. 每条总结都要有博主归属，且能在清单里找到
    orphan = [s for s in summaries if str(s.get("blogger_id") or "") not in bmap]
    if orphan:
        problems.append("%d 条总结的 blogger_id 不在博主清单里（首个：%s）"
                        % (len(orphan), orphan[0].get("aweme_id")))

    # 2. 全文同理
    orphan_t = [r for r in transcripts if str(r.get("blogger_id") or "") not in bmap]
    if orphan_t:
        problems.append("%d 条全文的 blogger_id 不在清单里（首个：%s）"
                        % (len(orphan_t), orphan_t[0].get("aweme_id")))

    # 3. 向量与总结必须逐行对齐：数量、顺序、id 全一致，否则会答成别人的视频
    meta = load(BASE / cfg["vector_meta"])
    ids = [str(x) for x in (meta.get("ids") or [])]
    bids = [str(x) for x in (meta.get("blogger_ids") or [])]
    sum_ids = [str(s.get("aweme_id")) for s in summaries]
    if len(ids) != len(sum_ids):
        problems.append("向量 %d 行 != 总结 %d 条，语义检索会漏，重建向量库" % (len(ids), len(sum_ids)))
    elif ids != sum_ids:
        bad = next((i for i, (a, b) in enumerate(zip(ids, sum_ids)) if a != b), 0)
        problems.append("向量 id 顺序与总结不一致（第 %d 行 %s != %s），重建向量库"
                        % (bad, ids[bad], sum_ids[bad]))
    if bids and len(bids) != len(ids):
        problems.append("vectors.json 的 blogger_ids 与 ids 长度不一致（%d vs %d）"
                        % (len(bids), len(ids)))
    elif bids:
        sum_by_id = {str(s.get("aweme_id")): s for s in summaries}
        for i, (bid, sid) in enumerate(zip(bids, ids)):
            s = sum_by_id.get(sid)
            if s and str(s.get("blogger_id") or "") != bid:
                problems.append("第 %d 行博主归属与总结不一致（向量 %s，总结 %s），重建向量库"
                                % (i, bid, s.get("blogger_id")))
                break

    # 4. 向量文件大小对不对
    _, note = check_vectors(cfg, len(ids), problems)

    # 5. 各博主条数与清单记录对不上（清单是打包时写的，用来对外报数）
    per = {}
    for s in summaries:
        bid = str(s.get("blogger_id") or "")
        per[bid] = per.get(bid, 0) + 1
    for bid, n in per.items():
        rec = (bmap.get(bid) or {}).get("counts") or {}
        want = rec.get("speech")
        if want and int(want) != n:
            problems.append("「%s」清单写 %s 条，实际 %d 条" %
                            ((bmap.get(bid) or {}).get("name", bid), want, n))
    empty = [b.get("name", "?") for b in bloggers if not per.get(str(b.get("id") or ""))]
    if empty:
        problems.append("这些博主一条可检索数据都没有：%s" % "、".join(empty))

    if problems:
        print("broken " + str(len(summaries)) + " summaries, " + str(len(transcripts))
              + " transcripts, " + str(len(ids)) + " vectors" + note
              + ", version " + str(cfg.get("version", "?")))
        for p in problems:
            print("  ✗ " + p)
        sys.exit(1)

    print("ok " + str(len(bloggers)) + " blogger(s), " + str(len(summaries))
          + " summaries, " + str(len(transcripts)) + " transcripts, "
          + str(len(ids)) + " vectors" + note + ", version "
          + str(cfg.get("version", "?")))
    for bid, n in sorted(per.items(), key=lambda kv: -kv[1]):
        print("  %s %s  %d 条" % ((bmap[bid].get("name") or bid), bid, n))

    # 有摘要但没全文是允许的（只建了向量没转写），但回答时取不到原文，要提示
    if transcripts and len(summaries) > len(transcripts):
        print("  warn 摘要 %d 条 > 全文 %d 条，多出来的取不到原文"
              % (len(summaries), len(transcripts)))


def check_vectors(cfg, n_rows, problems):
    """向量库：不加载矩阵（保持标准库），只校验文件大小对得上。"""
    vpath = BASE / cfg["vector_file"]
    meta = load(BASE / cfg["vector_meta"])
    dim = int(meta.get("dim") or 0)
    want = n_rows * dim * 2 + 128
    got = vpath.stat().st_size
    if dim and abs(got - want) > 128:
        problems.append("向量文件 %d 字节，按 %d×%d 应约 %d，可能没写完"
                        % (got, n_rows, dim, want))
        return len(meta.get("ids") or []), ""
    return len(meta.get("ids") or []), ""


if __name__ == "__main__":
    main()
