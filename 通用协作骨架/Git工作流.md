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

---

## ⚠️ 实测坑：代理环境变量会把 gh 挡住（2026-09-17）

**现象**：给 `gh` 加代理环境变量后，既连不上又会被误判为“登录失效”：

```bash
# ❌ 这么跑（当时 Clash 的 7899 端口并未监听）
HTTP_PROXY=http://127.0.0.1:7899 HTTPS_PROXY=http://127.0.0.1:7899 gh auth status
# → X Failed to log in … The token in keyring is invalid.
# → gh repo create 时报：proxyconnect tcp: dial tcp 127.0.0.1:7899: connectex: ...
```

**根因**：报错是 **proxyconnect 失败**，不是 token 真的失效。
gh 在代理不通时把这归因为登录失败，**误导性极强**（差一点就去让用户重新登录了）。

**实测结论（不带代理）**：

```bash
gh auth status   # ✓ Logged in to github.com account kongqiuran (keyring)，scopes: repo…
gh api user      # ✓ 正常返回登录名
git ls-remote https://github.com/...  # ✓ 直连可用（git config 里没有配代理）
```

**规矩**：
1. 本机 `gh` 与 `git` **直连 GitHub 可用**，不要无脑加 `HTTP_PROXY`／`HTTPS_PROXY`。
2. 只有在确实需要代理时（例：`raw.githubusercontent.com` 抽风）再临时加，**且用完就 `unset`**。
3. 看到 `gh` 说“keyring token invalid”时，**先看完整错误里有没有 `proxyconnect`**，
   再决定要不要重新登录——否则会把一个网络问题当成账号问题。
