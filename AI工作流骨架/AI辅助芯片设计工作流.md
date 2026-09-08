---
tags: [骨架, AI, LLM, EDA, 芯片设计, 前沿]
date: 2025-01-01
source: Awesome-LLM4EDA + ChipNeMo + RTLLM
---

# AI 辅助芯片设计工作流

> 大语言模型正在改变芯片设计的工作方式。这不是科幻，而是 2024-2025 年已经落地的前沿。
> 
> 本骨架整理自 GitHub 上的前沿项目（Awesome-LLM4EDA、ChipNeMo、RTLLM 等），
> 提炼出微电子学生可以**现在就用**的 AI 辅助策略。

---

## 为什么微电子学生要关注 LLM4EDA？

### 产业趋势
- NVIDIA 的 `ChipNeMo`：用领域自适应 LLM 辅助芯片设计，已在内部使用
- Synopsys、Cadence 都在集成 AI 助手
- **RTL 生成、布局优化、验证辅助**正在成为 AI 的游乐场

### 对学生的好处
- **加速学习**：用 AI 解释代码、推导公式、画流程图
- **降低实验门槛**：自然语言生成 Verilog/SPICE 网表
- **提前接触前沿**：LLM4EDA 是 EDA 的下一个范式

---

## 五大应用场景（来自 Awesome-LLM4EDA）

### 1. RTL 代码生成

**代表项目**：
- `RTLLM`：开源 RTL 生成基准，评估 LLM 写 Verilog 的能力
- `VeriGen`：专门训练用于 Verilog 生成的大模型
- `RTLcoder`：轻量级方案，性能超过 GPT-3.5

**你可以现在做的**：
```
Prompt: "写一个带异步复位的 4 位计数器 Verilog 模块，
         包含 testbench，并用中文注释解释时序逻辑"
```
- 用 AI 生成骨架代码，自己验证时序
- 对比 AI 生成的代码和自己写的，找出差异

---

### 2. 布局与物理设计

**代表项目**：
- `LayoutCopilot`：LLM 辅助模拟电路布局
- `ChatPattern`：用自然语言定制布局模式

**你可以现在做的**：
- 用 AI 解释版图设计规则（DRC、LVS）
- 让 AI 把自然语言描述转成初步布局草图

---

### 3. 验证与测试

**代表项目**：
- `AssertLLM`：从设计规格自动生成断言
- `LLM-Aided Testbench Generation`：自动生成 testbench
- `DIVAS`：SoC 安全分析

**你可以现在做的**：
```
Prompt: "为以下状态机生成 SystemVerilog testbench，
         包含随机激励和 covergroup"
```

---

### 4. EDA 工具交互

**代表项目**：
- `ChatEDA`：用自然语言操控 EDA 工具
- `EDA Corpus`：用于训练 LLM 与 OpenROAD 交互的数据集

**你可以现在做的**：
- 用 AI 帮你写 TCL/Python 脚本驱动 OpenROAD/Yosys
- 让 AI 解释 EDA 工具的日志输出

---

### 5. 知识获取与问答

**代表项目**：
- `RapidGPT`：HDL 设计的 AI 配对设计师
- 各种芯片设计领域的 ChatBot

**你可以现在做的**：
- 把数据手册丢给 AI，让它提取关键参数表
- 用 AI 对比不同代工厂的工艺参数

---

## 实用的 AI + 芯片设计工具链

| 工具/平台 | 用途 | 适合场景 |
|----------|------|---------|
| GitHub Copilot + Verilog | RTL 代码补全 | 日常编码 |
| Claude 3.5 Sonnet | 长上下文理解、复杂推理 | 架构设计、代码审查 |
| ChatGPT + Code Interpreter | 参数扫描、可视化 | 器件特性分析 |
| OpenROAD + AI 脚本 | 开源数字后端 | 学习完整流程 |
| Yosys + AI 网表生成 | 开源综合 | 理解综合过程 |

---

## 推荐的学习路径

### 阶段 1：用 AI 辅助理解（现在就能做）
- 用 AI 解释概念、推导公式、分析电路
- 用 AI 生成 LTspice/Verilog 骨架代码

### 阶段 2：用 AI 加速实验（有基础后）
- 用 AI 写 Python 脚本批量跑仿真
- 用 AI 辅助写 testbench
- 用 AI 解释 EDA 工具输出

### 阶段 3：探索 LLM4EDA 前沿（研究生/工作时）
- 读 Awesome-LLM4EDA 列表中的论文
- 尝试微调小模型用于特定任务（如特定工艺的 RTL 生成）
- 参与开源项目（OpenROAD、Yosys 的 AI 插件）

---

## 关键认知

### AI 不是替代，是增强
- AI 生成代码 → 你验证正确性
- AI 解释概念 → 你用自己的话重写进笔记
- AI 跑仿真 → 你分析结果、建立直觉

### AI 会犯错
- LLM 生成的 Verilog 可能有语法错误或逻辑 bug
- 必须跑仿真/综合验证
- **永远保持"不信任但验证"的态度**

---

## 关联骨架

- [[GitHub开源学习法]] —— 如何找到最新的 LLM4EDA 资源
- [[Obsidian-MOC-笔记体系]] —— 把 AI 输出整理进知识网络
- [[无板到板交接流程]] —— AI 辅助硬件验证的门禁规则
