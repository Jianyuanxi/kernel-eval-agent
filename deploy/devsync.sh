#!/bin/bash
# 把本地工作区（含未提交的改动）同步到服务器 ~/dev/<名字>/，用于在服务器上跑需要 Docker 的测试（块 3、4 常用）。
# 服务器访问不了 GitHub，所以不在服务器上 clone。
# 用法：bash deploy/devsync.sh 你的拼音名        例如 bash deploy/devsync.sh zhangsan
# 之后：ssh kernel-eval，cd ~/dev/zhangsan/backend，/opt/kernel-eval/venv/bin/python -m pytest tests/xxx
set -euo pipefail
NAME="${1:?用法：bash deploy/devsync.sh 你的拼音名}"
HOST="${HOST:-kernel-eval}"
cd "$(git rev-parse --show-toplevel)"
# 只传 git 管理的文件和未忽略的新文件（不传 .venv、samples、node_modules）
git ls-files -co --exclude-standard -z | tar --null -T - -czf .devsync.tar.gz
scp -q .devsync.tar.gz "$HOST:/tmp/devsync-$NAME.tar.gz"
rm -f .devsync.tar.gz
ssh "$HOST" "rm -rf ~/dev/$NAME && mkdir -p ~/dev/$NAME && tar -xzf /tmp/devsync-$NAME.tar.gz -C ~/dev/$NAME && rm /tmp/devsync-$NAME.tar.gz && echo 已同步到 ~/dev/$NAME"
