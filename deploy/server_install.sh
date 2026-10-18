#!/bin/bash
# 在服务器上运行（由 deploy.sh 调用）：装依赖、构建前端、替换代码、重启服务。
# 目录：/opt/kernel-eval/current 代码（每次整体替换） /opt/kernel-eval/venv Python 环境
#       /opt/kernel-eval/kernel-eval.env 配置（只在首次生成，之后手动改） /data/kernel-eval 数据
set -euo pipefail
NEW="$1"
VER="${2:-unknown}"
BASE=/opt/kernel-eval
PIP_INDEX=https://mirrors.cloud.tencent.com/pypi/simple

[ -d "$BASE/venv" ] || python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install -q -i "$PIP_INDEX" -r "$NEW/backend/requirements.txt"

if [ ! -f "$BASE/kernel-eval.env" ]; then
  sed "s/^KE_TOOL_TOKEN=.*/KE_TOOL_TOKEN=$(openssl rand -hex 16)/" "$NEW/deploy/env.example" > "$BASE/kernel-eval.env"
  echo "已生成 $BASE/kernel-eval.env，KE_TOOL_TOKEN 已随机生成"
fi

if [ -f "$NEW/frontend/package.json" ]; then
  (cd "$NEW/frontend" && npm ci --no-audit --no-fund --loglevel=error && npm run build)
else
  mkdir -p "$NEW/frontend/dist"
  echo '<!doctype html><meta charset="utf-8"><title>内核代码评测智能体</title><p>前端还没上线。后端状态：<a href="/api/health">/api/health</a>，接口文档：<a href="/docs">/docs</a></p>' \
    > "$NEW/frontend/dist/index.html"
fi
echo "$VER" > "$NEW/VERSION"

rm -rf "$BASE/previous"
[ -d "$BASE/current" ] && mv "$BASE/current" "$BASE/previous"
mv "$NEW" "$BASE/current"

sudo cp "$BASE/current/deploy/kernel-eval.service" /etc/systemd/system/kernel-eval.service
sudo cp "$BASE/current/deploy/nginx.conf" /etc/nginx/sites-available/kernel-eval
sudo ln -sf /etc/nginx/sites-available/kernel-eval /etc/nginx/sites-enabled/kernel-eval
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t -q
sudo systemctl daemon-reload
sudo systemctl enable -q kernel-eval
sudo systemctl restart kernel-eval
sudo systemctl reload nginx

for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1/api/health > /dev/null; then
    echo "部署完成：版本 $VER"; curl -s http://127.0.0.1/api/health; echo; exit 0
  fi
  sleep 1
done
echo "后端没起来，最近日志："; sudo journalctl -u kernel-eval -n 30 --no-pager; exit 1
