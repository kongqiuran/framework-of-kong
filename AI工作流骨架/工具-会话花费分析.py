# -*- coding: utf-8 -*-
"""
工具：分析某个项目的 AI 会话花费（配合骨架《AI会话成本控制》）

用途
----
回答三个问题：
  ① 这次会话花了多少、花在哪些环节？（新输入 / 输出 / 缓存重发）
  ② 上下文是怎么涨起来的？（账单 ≈ 调用次数 × 上下文规模 × 单价）
  ③ 有没有"缓存失效全价重发"这种隐形大坑？

原理
----
pi 把每次 API 调用的 usage 记在会话文件里：
    C:\\Users\\<用户名>\\.pi\\agent\\sessions\\<项目目录名>\\*.jsonl
每行一条消息；assistant 消息的 message.usage 里有
    input / output / cacheRead / cacheWrite / reasoning / totalTokens / cost{...}
本脚本把所有 assistant 消息的 usage 汇总，并按"轮次"和"时间桶"给出分布。

用法
----
    python 工具-会话花费分析.py                          # 自动用当前工作目录
    python 工具-会话花费分析.py --proj "D:\\A_lession\\数字信号处理"
    python 工具-会话花费分析.py --top 15                 # 只看最贵的 15 次调用
    python 工具-会话花费分析.py --session 2026-09-23     # 只分析某天的会话文件

注意
----
· cost 字段的货币单位由服务商决定（脚本只做汇总与占比，不做汇率换算）；
· "缓存失效"的判据：**新输入 > 5 万 且 缓存命中 < 2 万**（经验阈值，可自行调整）。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys


def sessions_root() -> pathlib.Path:
    """pi 的会话根目录：%USERPROFILE%\\.pi\\agent\\sessions"""
    return pathlib.Path(os.path.expanduser("~")) / ".pi" / "agent" / "sessions"


def proj_dir_name(cwd: str) -> str:
    """把项目路径转成 pi 用的目录名。规则：**把路径里的 ':' 与 '\\' 都换成 '-'**，
    首尾各补 '--'。例：
        D:\\A_lession\\数字信号处理  ->  --D--A_lession-数字信号处理--
        C:\\Users\\kongqiuran        ->  --C--Users-kongqiuran--
    """
    s = str(pathlib.Path(cwd).resolve())
    s = s.replace(":", "-").replace("\\", "-").replace("/", "-")
    return f"--{s}--"


def pick_session_files(root: pathlib.Path, proj: str | None, only: str | None) -> list[pathlib.Path]:
    if proj:
        d = root / proj_dir_name(proj)
        if not d.exists():                            # 允许直接传目录名
            d = root / proj
    else:
        d = root / proj_dir_name(os.getcwd())
    if not d.exists():
        print(f"找不到会话目录：{d}")
        print(f"可用目录（示例）：")
        for x in sorted(root.iterdir())[:15]:
            print("   ", x.name)
        sys.exit(1)
    files = sorted(d.glob("*.jsonl"))
    if only:
        files = [f for f in files if only in f.name]
    return files


def analyse(path: pathlib.Path, top: int) -> None:
    cost = collections.Counter()
    tok = collections.Counter()
    rows: list[dict] = []
    turns: list[tuple[int, float]] = []
    turn_no, cur = 0, 0.0
    buckets: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if d.get("type") != "message":
            continue
        m = d.get("message", {})
        if m.get("role") == "user":
            if turn_no:
                turns.append((turn_no, cur))
            turn_no += 1
            cur = 0.0
        u = m.get("usage")
        if isinstance(u, dict) and "cost" in u:
            c = u["cost"]
            cost.update({k: v for k, v in c.items() if isinstance(v, (int, float))})
            tok.update({k: v for k, v in u.items()
                        if isinstance(v, (int, float)) and k != "cost"})
            total = c.get("total", 0.0)
            cur += total
            ts = d.get("timestamp", "")
            buckets[ts[:15]]["cost"] += total
            buckets[ts[:15]]["calls"] += 1
            rows.append(dict(ts=ts[11:19],
                             ctx=u.get("input", 0) + u.get("cacheRead", 0),
                             inp=u.get("input", 0), out=u.get("output", 0),
                             cr=u.get("cacheRead", 0), c=total))
    if turn_no:
        turns.append((turn_no, cur))

    print(f"会话文件：{path.name}")
    print(f"API 调用次数：{len(rows)}")
    if not rows:
        print("（没有 usage 记录）")
        return
    print(f"上下文规模：{rows[0]['ctx']/1000:.1f}k → {rows[-1]['ctx']/1000:.1f}k"
          f"（平均 {sum(r['ctx'] for r in rows)/len(rows)/1000:.0f}k，峰值 "
          f"{max(r['ctx'] for r in rows)/1000:.0f}k）")

    print("\n=== 花费构成 ===")
    tot = cost.get("total", 0.0) or 1e-12
    for k in ("input", "output", "cacheRead", "cacheWrite"):
        print(f"  {k:<10}: {cost.get(k,0):.4f}  占 {cost.get(k,0)/tot:5.1%}")
    print(f"  {'总计':<10}: {cost.get('total',0):.4f}")

    print("\n=== token 构成 ===")
    for k in ("input", "output", "reasoning", "cacheRead", "totalTokens"):
        if tok.get(k):
            print(f"  {k:<12}: {tok[k]:,}")
    print(f"  缓存重发占全部 token：{tok.get('cacheRead',0)/max(1,tok.get('totalTokens',1)):.1%}")

    print("\n=== 最贵的调用 ===")
    for i, r in enumerate(sorted(rows, key=lambda x: -x["c"])[:top], 1):
        flag = "  ⚠缓存失效全价重发" if (r["inp"] > 50_000 and r["cr"] < 20_000) else ""
        print(f"  {i:>2}. {r['ts']}  上下文 {r['ctx']/1000:6.1f}k  "
              f"新输入 {r['inp']:>8,}  缓存 {r['cr']:>8,}  输出 {r['out']:>6,}  "
              f"花费 {r['c']:.4f}{flag}")

    cache_miss = [r for r in rows if r["inp"] > 50_000 and r["cr"] < 20_000]
    if cache_miss:
        s = sum(r["c"] for r in cache_miss)
        print(f"\n  ⚠ 检出 {len(cache_miss)} 次“缓存失效全价重发”，合计 {s:.4f}"
              f"（占总花费 {s/tot:.1%}）—— 典型原因是会话闲置后继续。")

    print("\n=== 每一轮对话（轮次 = 用户消息）===")
    for n, c in turns:
        print(f"  第 {n:>2} 轮: {c:.4f}")

    print("\n=== 时间桶（10 分钟）===")
    for k in sorted(buckets):
        print(f"  {k}  {buckets[k]['calls']:>3} 次调用  {buckets[k]['cost']:.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="分析 pi 会话花费")
    ap.add_argument("--proj", default=None, help="项目目录（默认当前目录）")
    ap.add_argument("--session", default=None, help="只分析文件名含该字符串的会话")
    ap.add_argument("--top", type=int, default=10, help="列出最贵的 N 次调用（默认 10）")
    args = ap.parse_args()

    root = sessions_root()
    if not root.exists():
        print(f"会话根目录不存在：{root}")
        return 1
    files = pick_session_files(root, args.proj, args.session)
    if not files:
        print("没有匹配的会话文件")
        return 1
    for f in files:
        print("=" * 74)
        analyse(f, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
