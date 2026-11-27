# 给 AI 智能体：安装这个技能

用户让你「从这个 GitHub 地址安装技能」时，按本文件执行，不要自行发挥。

本仓库是一个 WorkBuddy 技能包，技能名 `masculine-awakening`，装好后可在对话框里直接问
「潇洒哥怎么看待彩礼」这类问题，答案带博主、日期、标题、链接。

## 目标位置（唯一正确位置）

- macOS / Linux / Git Bash：`~/.workbuddy/skills/masculine-awakening`
- Windows：`%USERPROFILE%\.workbuddy\skills\masculine-awakening`

**禁止装到系统临时目录**（`/tmp`、`%TEMP%`、`AppData\Local\Temp`）。
装在那里，用户重启或清理磁盘后技能就消失了——这是最常见的失败方式。

## 执行

原样运行下面一条命令，**不要自己下载 zip 再解压**：

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/ydaydayup/masculine-awakening@main/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://cdn.jsdelivr.net/gh/ydaydayup/masculine-awakening@main/install.ps1 | iex
```

脚本内部已处理：CDN 失败自动换源、下载中断重试、旧版本自动备份、
拦截临时目录、检查 numpy / fastembed、跑数据自检。不需要你补任何步骤。

## 装完必须验证并报告

1. 列出 `~/.workbuddy/skills/masculine-awakening/`，确认 `SKILL.md`、`scripts/`、`data/` 都在
2. 运行 `python ~/.workbuddy/skills/masculine-awakening/scripts/check.py`
   —— 正常输出包含 **1273 条口播**，且没有报错
3. 把「安装路径 + 自检结果」如实报告给用户

## 不要做的事

- 不要把技能放临时目录，即使你的工作目录本来就在临时目录里
- 不要修改 `SKILL.md` 里的 `name` 字段
- 不要清空或改动 `data/` —— 那是问答用的 6MB 数据，删了就没有答案了
- 不要额外安装依赖，只需要 `requirements.txt` 里的 `numpy` 和 `fastembed`

## 报错对照

| 现象 | 原因与处理 |
|---|---|
| 包里找不到 `masculine-awakening` 目录 | jsDelivr 节点还没刷新，把 URL 里的 `cdn` 换成 `fastly` 或 `testingcf` 重试 |
| 下载中断 / `schannel: missing close_notify` | 网络中断，脚本会自动换 codeload 源；重跑一次即可 |
| 没有 curl | Windows 改用上面的 PowerShell 版本 |
| 缺 fastembed | `python -m pip install -r <技能目录>/requirements.txt`，首次检索会下载约 100MB 向量模型 |
