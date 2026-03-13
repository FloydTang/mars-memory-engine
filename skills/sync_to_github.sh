#!/bin/bash
# Mars Mirror Sync - GitHub Backup Script
# 功能: 自动备份 Mars Workspace 到 GitHub
# 触发: 每日 00:00 通过 OpenClaw Cron

set -e

# 配置
WORKSPACE="/root/.openclaw/agents/main/workspace"
REPO_URL="https://github.com/FloydTang/openclaw-config.git"
BRANCH="main"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
DATE=$(date +"%Y-%m-%d")

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Mars Mirror Sync - Daily Backup${NC}"
echo "======================================"
echo "时间: $TIMESTAMP"
echo "工作目录: $WORKSPACE"
echo ""

# 进入工作目录
cd "$WORKSPACE"

# 检查 Git 状态
echo -e "${YELLOW}📋 检查 Git 状态...${NC}"
if [ -d .git ]; then
    echo "✅ Git 仓库已初始化"
else
    echo "📝 初始化 Git 仓库..."
    git init
fi

# 检查远程仓库
echo -e "${YELLOW}🔗 检查远程仓库...${NC}"
if git remote | grep -q "origin"; then
    echo "✅ 远程仓库已配置"
    git remote -v
else
    echo "❌ 远程仓库未配置，请检查配置"
    exit 1
fi

# 获取远程更新
echo -e "${YELLOW}📥 获取远程更新...${NC}"
git fetch origin $BRANCH 2>/dev/null || echo "⚠️ 无法获取远程更新（可能首次推送）"

# 添加所有更改
echo -e "${YELLOW}📦 添加文件到暂存区...${NC}"
git add -A

# 检查是否有更改需要提交
if git diff --cached --quiet; then
    echo -e "${GREEN}✅ 工作目录干净，无需提交${NC}"
    exit 0
fi

# 统计更改
echo -e "${YELLOW}📊 更改统计:${NC}"
git diff --cached --stat

# 提交更改
echo -e "${YELLOW}💾 提交更改...${NC}"
git commit -m "Daily Mars Heartbeat - $DATE

自动备份时间: $TIMESTAMP
备份内容:
- 记忆文件更新
- 系统配置变更
- 主题文档同步
- Skill 更新

由 Mars Mirror Sync 自动生成" || {
    echo -e "${RED}❌ 提交失败${NC}"
    exit 1
}

# 推送到远程
echo -e "${YELLOW}📤 推送到 GitHub...${NC}"
git push origin $BRANCH || {
    echo -e "${RED}❌ 推送失败${NC}"
    echo "可能的解决方案:"
    echo "1. 检查 GitHub Token 是否有效"
    echo "2. 检查网络连接"
    echo "3. 检查仓库权限"
    exit 1
}

echo ""
echo -e "${GREEN}✅ 同步完成!${NC}"
echo "======================================"
echo "提交时间: $(date +"%Y-%m-%d %H:%M:%S")"
echo "提交信息: Daily Mars Heartbeat - $DATE"
echo "远程仓库: $REPO_URL"
echo "分支: $BRANCH"

# 记录同步日志
mkdir -p logs
echo "[$TIMESTAMP] 同步成功 - $(git rev-parse --short HEAD)" >> logs/sync_history.log

exit 0
