#!/bin/bash
# 在开发机（Git Bash / WSL / Linux）上运行：把 main 分支打包传到服务器并安装重启。
# 服务器访问不了 GitHub，所以不在服务器上 git pull。
# 用法：bash deploy/deploy.sh            部署 origin/main（正式部署只用这个）
#       REF=HEAD bash deploy/deploy.sh   部署本地当前提交（只在调试部署脚本时用）
# 前提：~/.ssh/config 里配好了 Host kernel-eval（见 docs/05-服务器与环境.md）
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
REF="${REF:-origin/main}"
HOST="${HOST:-kernel-eval}"
[ "$REF" = "origin/main" ] && git fetch -q origin main
echo "部署 $REF ($(git rev-parse --short "$REF")) 到 $HOST"
git archive --format=tar.gz -o deploy-upload.tar.gz "$REF"
scp -q deploy-upload.tar.gz "$HOST:/tmp/kernel-eval.tar.gz"
rm -f deploy-upload.tar.gz
ssh "$HOST" "rm -rf /tmp/ke-new && mkdir -p /tmp/ke-new && tar -xzf /tmp/kernel-eval.tar.gz -C /tmp/ke-new && bash /tmp/ke-new/deploy/server_install.sh /tmp/ke-new $(git rev-parse --short "$REF")"
