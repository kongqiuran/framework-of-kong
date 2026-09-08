---
tags: [骨架, Git, 版本控制, 协作]
date: 2025-01-01
source: 综合实践
---

# 骨架：Git 工作流

> 适用于：所有需要版本控制的项目。

---

## 基本工作流

```bash
# 1. 日常开发
cd "D:/your-project"
# 编辑文件...

# 2. 查看状态
git status

# 3. 暂存本次改动（只加相关文件）
git add file1 file2

# 4. 提交
git commit -m "type: 简短描述

详细说明（可选）"

# 5. 推送到远程
git push origin main
```

---

## 提交信息规范

```
type: 主题（不超过50字）

- 详细说明1
- 详细说明2

相关: #issue编号
```

| type | 含义 |
|-----|------|
| `feat` | 新功能 |
| `fix` | 修复 |
| `docs` | 文档 |
| `style` | 格式（不影响代码逻辑） |
| `refactor` | 重构 |
| `test` | 测试 |
| `chore` | 构建/工具 |
| `init` | 初始化 |

---

## 分支策略（简化版）

```
main
  ├── feat/xxx      # 功能开发
  ├── fix/xxx       # 修复
  ├── docs/xxx      # 文档
  └── hotfix/xxx    # 紧急修复
```

- 个人项目：main 直接开发即可
- 团队项目：用 Pull Request / Merge Request

---

## 与 AI 协作时的 Git 规范

1. **AI 自动执行**：`git add` + `git commit`
2. **AI 不得自动执行**：`git push`（需用户确认）
3. **提交后必须告知**：
   - "已经 git add，git commit 了"
   - 提交哈希和提交说明
4. **不是 Git 仓库时**：明确报告，不得擅自 `git init`

---

## 多项目改动

跨多个项目改动时：
- 分别说明每个项目的改动内容
- 分别执行 git status / add / commit
- 分别报告提交结果

---

## 紧急回退

```bash
# 查看历史
git log --oneline

# 软回退（保留改动）
git reset --soft HEAD~1

# 硬回退（丢弃改动，慎用）
git reset --hard HEAD~1

# 查看所有操作记录（包括 reset）
git reflog
```
