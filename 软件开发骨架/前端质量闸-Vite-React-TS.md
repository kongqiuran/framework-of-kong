---
tags: [骨架, 前端, 质量闸, Vite, React, TypeScript]
date: 2026-10-07
source: learning-os V4 `T01` 实测（该版本组合经 lint / typecheck / test / build 四道检查＋CI 实跑验证）
---

# 骨架：前端质量闸（Vite + React + TypeScript）

> 适用于：纯客户端 SPA 新项目起步。
> 目标：**在写第一行业务代码之前**，先把「版本纪律 + 四道检查 + CI 阻断」立起来。

---

## 1. 三条纪律先立（比配置本身更重要）

| # | 纪律 | 为什么 |
|---|---|---|
| 1 | **版本钉死**：`package.json` 写精确版本（`"react": "19.3.0"`），不用 `^`；`package-lock.json` 入库 | `^` 会让不同机器装到不同小版本 → "我这儿是好的"；上游为规避渲染引擎 bug 静默改行为时，版本漂移会让归因无从下手 |
| 2 | **升级 = 独立动作**：升级前写清单（版本 → 差异 → 归因），升级后重跑差分与走查，不混在功能提交里 | 框架 major 间隔 2–3 年，升级是事件不是日常 |
| 3 | **不用 `rc` / `beta` / `next`** | 主流框架里"主线前的大版本长期 RC"不只一例；新项目没必要背这个风险 |

## 2. 装版本前必须查 peer（真实踩坑）

选组合**不能只看 `npm view <pkg> version`**，要先查兼容边界：

```bash
npm view typescript-eslint@<版本> peerDependencies
npm view @vitejs/plugin-react@<版本> peerDependencies
```

**真实一例（2026-10）**：`typescript-eslint` 的 peer 声明是 `typescript: ">=4.8.4 <6.1.0"`，
而 npm 上 `typescript@latest` 已经是 **7.x** → 直接把"最新的都装上"会得到一个不兼容组合。
正确做法：选满足 peer 上限的版本（本例 TS **6.0.3**）并在 lockfile 里锁住。

## 3. 实测可用组合（2026-10-07）

| 包 | 版本 | 备注 |
|---|---|---|
| react / react-dom | 19.3.0 | 纯 SPA；不用 SSR / RSC / Server Actions / 元框架 |
| vite | 8.3.3 | 需要 Node ≥ 22.12 |
| @vitejs/plugin-react | 6.1.2 | peer 要求 `vite ^8`（配 vite 7 须换 5.x） |
| typescript | 6.0.3 | 受 typescript-eslint peer 上限约束 |
| eslint | 10.12.0 | flat config |
| typescript-eslint | 8.71.1 | |
| eslint-plugin-react-hooks | 7.1.1 | |
| vitest | 5.0.3 | 支持 vite ^6.4 / ^7 / ^8 |
| @types/react / @types/react-dom | 19.3.0 | |

## 4. 四道检查（缺一不可）

```json
"scripts": {
  "dev": "vite",
  "build": "tsc --noEmit && vite build",
  "lint": "eslint .",
  "typecheck": "tsc --noEmit",
  "test": "vitest run"
}
```

## 5. 关键配置要点（附踩坑）

### `tsconfig.json`
- **单文件配置**，不用 project references：`composite` + `noEmit` 的组合有坑，起步阶段不值得
- `"moduleResolution": "bundler"`（按打包器规则解析，支持 package.json `exports`）
- `"jsx": "react-jsx"`（新转换，文件里无需 `import React`）
- 严格性尽量拉满：`strict` / `noUnusedLocals` / `noUncheckedIndexedAccess` / `exactOptionalPropertyTypes` / `verbatimModuleSyntax`
- `"types": []` + 三斜线按需引用，避免全局类型污染

> **坑（TS 6 的 TS2882）**：`import './app.css'` 会报
> "Cannot find module or type declarations for side-effect import"。
> **修法**：加 `src/vite-env.d.ts`，内容一行 `/// <reference types="vite/client" />`。

### `eslint.config.js`（flat config 三件套）
`js.configs.recommended` + `...tseslint.configs.recommended` + `reactHooks.configs.recommended.rules`。

### `vite.config.ts`
`test` 字段写在 Vite 配置里时，`defineConfig` 要**从 `vitest/config` 导入**（不是 `vite`），否则没有类型提示。

## 6. 测试怎么起步最省（少两个依赖）

骨架阶段用 `react-dom/server` 的 `renderToStaticMarkup` 断言首屏 HTML 即可，
**不必立刻引入 jsdom / @testing-library**——等出现真实交互测试再加。

## 7. 其他实践

- **开发构建必须开 `StrictMode`**，把双调用当正常态（提前暴露不纯代码与重复副作用）
- `server.host = true`：便于局域网真机走查（iPad / 手机）
- 中文字体回退链写进 CSS：`system-ui` → `PingFang SC` → `Microsoft YaHei` → `sans-serif`
- CI 一律 `npm ci`（严格按 lockfile），不用 `npm install`
