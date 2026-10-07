# 许可闸脚本（骨架版）

> 配套文档：[`../许可登记与署名闸.md`](../许可登记与署名闸.md)（机制与纪律）
> 来源：learning-os V4 `T01`（`tools/license-manifest/`），仅改了文件头说明，逻辑一致。
> **只用 Python 标准库**（不占项目依赖预算）；注入用例需要 `pytest`。

## 两个文件

| 文件 | 作用 |
|---|---|
| `license_manifest.py` | 六模式脚本：`--generate` / `--check` / `--notices` / `--check-build <dist>` / `--verify-text` / `--budget` |
| `test_injections.py` | 11 条注入用例 ＋ 对照组（证明防线真的会红，且不会永远红） |

## 换项目时的适配点（三处）

| # | 位置 | 说明 |
|---|---|---|
| 1 | `WEB_DIR` / `SERVER_DIR` | 默认假设仓库内有 `web/`（npm 前端）与 `server/`（pip 后端）；只有一边也能跑 |
| 2 | `TOOL_PACKAGES` | 预算桶 `tool`（lint / test / 类型检查类包）的成员名单 |
| 3 | `parents[2]` | 脚本须放在 `<仓库>/tools/<任意目录>/` 下；层级不同要改 |

另外还依赖两个约定：

- 前端 `web/package.json` 的 `dependencies` / `devDependencies`（直接依赖清单）；
- 后端 `server/requirements.txt` ＋ `requirements-dev.txt`（`==` 钉版本），
  且依赖元数据可读（本机 venv 或 CI 里先 `pip install`）。

## 建议用法

```bash
# ① 首次：装好两侧依赖后生成草稿
python tools/许可闸/license_manifest.py --generate
# ② 人工复核：看 spdx 是否出现 <待人工确认>；自由文本必须打开许可原文核实
# ③ 生成公开文档
python tools/许可闸/license_manifest.py --notices
# ④ 自检（与 CI 同一套判据）
python tools/许可闸/license_manifest.py --check
python tools/许可闸/license_manifest.py --verify-text     # 打印逐条对照明细
python tools/许可闸/license_manifest.py --budget
# ⑤ 防线自测
python -m pytest tools/许可闸/test_injections.py -q
```

CI 里建议两步都跑：`--check`（静默失败即红）＋ 注入用例（证明检查本身有效）。
构建后追加 `--check-build <dist>` 作为构建期阻断。
