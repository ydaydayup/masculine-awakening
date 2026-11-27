#!/usr/bin/env bash
# blogger-kb 一键安装脚本（macOS / Linux / Windows Git Bash）
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/blogger-kb/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- /自定义/技能目录
set -euo pipefail

REPO="ydaydayup/masculine-awakening"
BRANCH="main"
SKILL="blogger-kb"

SKILLS_DIR="${WORKBUDDY_SKILLS:-$HOME/.workbuddy/skills}"
TARGET="${1:-}"

say()  { printf '%s\n' "$*"; }
step() { printf '  - %s\n' "$*"; }
die()  { printf '\n出错了：%s\n' "$*" >&2; exit 1; }

say ""
say "blogger-kb 安装器"
say ""

command -v curl >/dev/null 2>&1 || die "没找到 curl。macOS/Linux 一般自带；Windows 请改用 install.ps1"
command -v tar  >/dev/null 2>&1 || die "没找到 tar，装好再来"

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t bloggerkb)"
cleanup() { rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# 下载源按顺序尝试。github.com 的 archive 会 302 到 codeload，国内偶有中断
# （schannel: missing close_notify），直连 codeload 往往能过，所以两个都留。
step "下载 ${REPO}"
CANDS=()
[ -n "${BLOGGER_KB_URL:-}" ] && CANDS+=("$BLOGGER_KB_URL")
CANDS+=("https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz")
CANDS+=("https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}")

GOT=""
for u in "${CANDS[@]}"; do
  if curl -fsSL --retry 2 --retry-delay 2 --max-time 300 -o "$TMP/pkg.tar.gz" "$u" 2>/dev/null; then
    GOT="$u"
    break
  fi
  step "这个源没通，换下一个"
done
[ -n "$GOT" ] || die "所有下载源都没成功。检查网络，或手动下载：https://github.com/${REPO}"

step "解包"
# 必须先进目录再解，否则 Windows 下 GNU tar 会把 "C:" 当远程主机名。
( cd "$TMP" && tar -xzf pkg.tar.gz ) || die "解包失败，tar 包可能损坏"

SRC="$(find "$TMP" -maxdepth 3 -type d -name "$SKILL" -not -path "*/.*" | head -1)"
[ -n "$SRC" ] || die "包里找不到 ${SKILL} 目录"

if [ -n "$TARGET" ]; then
  DEST="$TARGET"
else
  DEST="$SKILLS_DIR/$SKILL"
fi

mkdir -p "$(dirname "$DEST")"

if [ -e "$DEST" ]; then
  BACKUP="${DEST}.bak.$(date +%Y%m%d%H%M%S)"
  mv "$DEST" "$BACKUP"
  step "已存在旧版本，备份到 ${BACKUP}"
fi

cp -R "$SRC" "$DEST" || die "复制失败，检查目标目录权限"
step "装到 $DEST"

say ""
say "检查运行环境..."

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  say "  ! 没找到 python，问答功能跑不起来。装好 Python 3.9+ 再执行："
  say "    pip install -r \"$DEST/requirements.txt\""
else
  if "$PY" -c "import numpy" >/dev/null 2>&1; then
    step "numpy 已就绪"
  else
    say "  ! 缺 numpy，执行：$PY -m pip install -r \"$DEST/requirements.txt\""
  fi
  if "$PY" -c "import fastembed" >/dev/null 2>&1; then
    step "fastembed 已就绪"
  else
    say "  ! 缺 fastembed（语义检索要用），执行："
    say "    $PY -m pip install -r \"$DEST/requirements.txt\""
    say "    首次检索会自动下载约 100MB 的中文向量模型"
  fi

  if [ -f "$DEST/scripts/check.py" ]; then
    say ""
    say "数据自检："
    if "$PY" "$DEST/scripts/check.py" 2>/dev/null | sed 's/^/    /'; then
      :
    else
      say "    ! 自检没通过，见上面的报错"
    fi
  fi
fi

if [ -n "$TARGET" ]; then
  say ""
  say "注意：这次装到了自定义目录，WorkBuddy 不会自动加载。"
  say "要用的话把整个目录挪到 $SKILLS_DIR/ 下面。"
fi

say ""
say "装好了。打开 WorkBuddy 直接问即可，例如："
say "  「潇洒哥怎么看待彩礼」"
say ""
