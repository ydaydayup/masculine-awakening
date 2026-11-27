# masculine-awakening · 男性觉醒博主观点集合

把男性觉醒赛道博主的口播视频，做成一个可以提问的本地智库。

答案严格限定在他们讲过的原话里，出处带博主、日期、标题和链接；没讲过的，直接说没讲过。不是让 AI 点评这些观点，而是把「谁在哪条视频里、原话怎么说的」准确找出来。

全程离线运行，不联网、不调 API。装好就能问。

> 仓库名、技能名、安装目录三者统一为 `masculine-awakening`。装完在 `~/.workbuddy/skills/masculine-awakening/`，WorkBuddy 里触发的技能名也是它，不用记两套名字。

---

## 一键安装

**macOS / Linux / Git Bash**

```bash
curl -fsSL https://fastly.jsdelivr.net/gh/ydaydayup/masculine-awakening@main/install.sh | bash
```

**Windows PowerShell**

```powershell
irm https://fastly.jsdelivr.net/gh/ydaydayup/masculine-awakening@main/install.ps1 | iex
```

> 安装脚本走 jsDelivr，国内可直接访问；数据包从 github.com 下载，带重试和备用源。
> 如果 jsDelivr 打不开，把地址换成 `https://raw.githubusercontent.com/ydaydayup/masculine-awakening/main/install.sh`（海外更快，国内可能需要代理）。

装到 `~/.workbuddy/skills/masculine-awakening/`（Windows 是 `%USERPROFILE%\.workbuddy\skills\masculine-awakening`）。

装完重开 WorkBuddy，直接问就行：

> 潇洒哥怎么看待彩礼？
> 他说过什么关于二婚的原话？

## 依赖

只依赖两个 Python 包，脚本会自动检查：

```bash
pip install -r ~/.workbuddy/skills/masculine-awakening/requirements.txt
```

- `numpy` —— 向量相似度计算
- `fastembed` —— 把问题编码成向量

首次检索会下载约 100MB 的中文向量模型（`BAAI/bge-small-zh-v1.5`），之后就缓存在本地。

如果 `fastembed` 装不上，检索功能不可用，但 `read.py` 浏览原文仍然可用。

## 收录的博主

目前收了这一类博主里的第一位。新博主会持续并进来，每次更新整库重打，原有内容不受影响。

| 博主 | 别名 | 条数 | 字数 | 时间跨度 |
|---|---|---|---|---|
| 潇洒哥涂龙 | 潇洒哥、涂龙、屠龙、拉闸哥、拉哥、扎哥 | 1273 条 | 108.8 万字 | 2024-12-13 ~ 2026-11-26 |

每条视频两份数据：一段约 84 字的内容总结（用来检索），和一份完整的逐字口播稿（用来作答）。

## 工作方式

```
你的问题 → 编码成 512 维向量
        → 与 1273 条总结向量比对，取高分
        → 按 id 取回那几条的完整口播稿
        → 模型只根据这些原文回答
```

关键点：**总结只当索引，从不进答案**。检索命中的视频，交给模型的是完整原文，不是摘要、不是片段。

两道拒答门槛：

- 最高分低于 `vector_min_score`（0.58）→ 判定没讲过
- 话题相关但具体事没讲过（擦边）→ `out_of_scope` 拦下

所以它不会拿常识补内容，也不会把别人的观点安到这位博主头上。

## 命令行用法

装好后可以直接调用，不必经过 WorkBuddy：

```bash
cd ~/.workbuddy/skills/masculine-awakening

python scripts/check.py                              # 数据完整性自检
python scripts/read.py --bloggers                    # 看看收了谁、多少条
python scripts/read.py --search "彩礼"                # 关键词找原话
python scripts/retrieve.py "彩礼" --sem --list 5      # 语义检索，只回候选摘要
python scripts/retrieve.py "彩礼" --sem               # 直接连完整原文一起回
python scripts/retrieve.py --pick 7544659445029932347 # 按 id 取全文
```

所有输出都是 JSON，方便接到自己的流程里。

## 目录结构

```
masculine-awakening/
├── SKILL.md                 技能说明，WorkBuddy 靠它决定何时触发
├── config.json              阈值、域外黑名单、文件路径
├── requirements.txt
├── scripts/
│   ├── core.py              配置加载、博主匹配
│   ├── semantic.py          向量检索核心
│   ├── retrieve.py          召回 + 取原文
│   ├── read.py              浏览目录、找原话
│   └── check.py             四份数据的一致性校验
├── references/
│   └── answer-rules.md      回答规则、归属判定、冲突处理
└── data/
    ├── bloggers.json        博主清单
    ├── summaries.json       1273 条总结
    ├── transcripts.jsonl    1273 条完整口播稿
    ├── vectors.npy          1273 × 512 向量矩阵
    └── vectors.json         向量元数据
```

`vectors.npy` 第 n 行、`vectors.json` 的 `ids[n]`、`summaries.json` 第 n 条，三者必须严格一一对应。`check.py` 会逐行比对，错行不报错但会答错人，所以改动数据后务必重跑自检。

## 自己做一位博主

这个仓库只带了潇洒哥涂龙的现成数据。想给自己关注的博主建一个，需要完整流水线：

1. 抓到该博主的视频列表和音频（爬虫不在本仓库内）
2. 语音转写，得到逐字稿
3. 每条写一段总结
4. 向量化
5. 标定阈值、打包

工具链暂未开源：抓取、语音转写、逐条写总结、向量化、阈值标定，目前是作者本地的流水线。需要给新的博主建库，可以提 issue 说明需求。

## 卸载

```bash
rm -rf ~/.workbuddy/skills/masculine-awakening
```

Windows：

```powershell
Remove-Item "$env:USERPROFILE\.workbuddy\skills\masculine-awakening" -Recurse -Force
```

## 授权

分两部分，别混淆：

**代码**（`scripts/`、`SKILL.md`、`references/`、安装脚本）—— MIT 许可，随便用、改、商用。

**数据**（`data/` 下的总结、口播稿、向量）—— **不适用 MIT**。这些内容整理自「潇洒哥涂龙」在抖音公开发布的视频，文字著作权归原作者所有。本仓库仅作个人学习与检索研究之用，**不得用于商业用途、不得二次分发、不得用于训练模型**。

如果你是原作者或权利人，认为本仓库侵犯了你的权益，提一个 issue，我会在 48 小时内移除相关内容。

检索得到的任何观点都是原作者的观点，与本项目无关。这个工具只负责「准确转述他讲过什么」，不负责判断对错。
