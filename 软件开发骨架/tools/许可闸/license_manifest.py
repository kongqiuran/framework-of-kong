#!/usr/bin/env python
"""许可登记与生成脚本（骨架版，通用化自 learning-os 的 `T-01` 脚本）。

**换项目时先改这三处适配点**：
1. `WEB_DIR` / `SERVER_DIR`：默认假设仓库内有 `web/`（npm 前端）与 `server/`（pip 后端）两个目录；
   只有一边也能用（另一边读不到依赖清单即返回空）；
2. `TOOL_PACKAGES`：预算桶 `tool` 的成员名单（lint / test / 类型检查类包）；
3. 脚本需放在 `<仓库>/tools/<任意目录>/xxx.py`（靠 `parents[2]` 定位仓库根），层级不同要改。

其余逻辑与 learning-os 实际使用版一致（仅改了文件头这段说明）。

职责：

1. `--generate`：从**依赖元数据**（前端 node_modules/package.json、后端 dist-info/METADATA）
   生成或更新 `licenses/manifest.json` 草稿——版本与许可字段取自实际安装的包，不靠记忆；
2. `--check`：机械核对（CI 闸 2 用）——清单一致性 + 三层许可字段完整性 + 判据 `b`/`c`；
3. `--check-build <dist>`：闸 3——构建产物中找不到强制署名文案则**非零退出**（判据 `d`）；
4. `--notices`：由 manifest 生成 `THIRD-PARTY-NOTICES.md`（落点 ②，判据 `c` 的文本）；
5. `--budget`：按 scope 统计三个依赖预算桶（docs/plan/03 §5.2）。

设计纪律：
- **只用标准库**：本脚本是工具，不占依赖预算（03 §5.2 三个桶都不含它）；
- **不猜**：读不到的字段写显式占位符（如 `<待人工确认>`），`--check` 会因占位符失败；
- **只增不减**：`--generate` 保留 manifest 中已有人工字段（owner / usage / additional_terms 等），
  只刷新版本与许可元数据。

用法：
    python tools/license-manifest/t01_licenses.py --generate
    python tools/license-manifest/t01_licenses.py --check
    python tools/license-manifest/t01_licenses.py --notices
    python tools/license-manifest/t01_licenses.py --check-build web/dist
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

# ---- 路径锚点（相对本文件定位，保证在任何工作目录下运行结果一致）------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "licenses" / "manifest.json"
NOTICES_PATH = REPO_ROOT / "THIRD-PARTY-NOTICES.md"
WEB_DIR = REPO_ROOT / "web"
WEB_NODE_MODULES = WEB_DIR / "node_modules"
SERVER_DIR = REPO_ROOT / "server"
SERVER_VENV_SITE = SERVER_DIR / ".venv" / "Lib" / "site-packages"  # Windows 布局
SERVER_VENV_SITE_POSIX = SERVER_DIR / ".venv" / "lib"  # Linux/macOS 布局（CI 用）

# 跨工程通用的 lint / test / 类型检查类工具 → 进 "tool" 预算桶（03 §5.2 第三个桶）
TOOL_PACKAGES = {
    "eslint",
    "@eslint/js",
    "typescript-eslint",
    "eslint-plugin-react-hooks",
    "vitest",
    "pytest",
    "pytest-django",
    "ruff",
    "mypy",
}

# 显式占位符：出现在 manifest 里表示"必须由人补全"，`--check` 见到即失败
PLACEHOLDER = "<待人工确认>"

# SPDX 表达式形态（含 AND / OR / WITH 组合）；用于识别元数据里的自由文本（如 pytest-django）
SPDX_EXPRESSION = re.compile(r"^[A-Za-z0-9.+-]+(\s+(WITH|AND|OR)\s+[A-Za-z0-9.+-]+)*$")

# 需要提示人工复核的"额外声明"文件名（含 Apache-2.0 的 ThirdPartyNotice 变体）
NOTICE_CANDIDATES = ("NOTICE", "NOTICE.md", "NOTICE.txt", "ThirdPartyNoticeText.txt", "ThirdPartyNotices.txt")


def is_spdx_expression(value: str) -> bool:
    """判断一个值是否长得像合法 SPDX 表达式（如 `MIT`、`LGPL-3.0-only`、`Apache-2.0`）。

    用途：依赖元数据里的 `License` 字段经常是自由文本（一句话），
    这种值不能直接当作许可结论写进 manifest——必须人工核实后填标准 SPDX。
    """
    return bool(SPDX_EXPRESSION.match(value.strip()))


def resolve_spdx(meta_spdx: str, existing_spdx: str | None) -> str:
    """决定写进 manifest 的 SPDX 值：

    1. 元数据里是合法 SPDX → 信任元数据（每次生成自动刷新）；
    2. 元数据不是合法 SPDX，但 manifest 里已有人工核实过的合法值 → **保留人工值**（防止覆盖）；
    3. 两者都不可用 → 写占位符（`--check` 会失败，强制人工处理）。
    """
    if is_spdx_expression(meta_spdx):
        return meta_spdx
    if existing_spdx and is_spdx_expression(existing_spdx):
        return existing_spdx
    return PLACEHOLDER

# 工具运行期不需要的字段（生成时给默认值）
DEFAULT_OWNER = "待指派"  # T01 阶段唯一负责人是项目发起人；正式责任人待团队成型后补


def normalize(name: str) -> str:
    """依赖名归一化（PEP 503）：比较时不区分大小写，`_`/`.`/`-` 视为等价。"""
    return re.sub(r"[-_.]+", "-", name).lower()


# ---- 依赖清单读取 ---------------------------------------------------------------


def read_frontend_deps() -> dict[str, dict[str, str]]:
    """读前端直接依赖。

    返回 {包名: {"version": 精确版本, "kind": "dependencies"|"devDependencies"}}。
    来源：web/package.json（直接依赖清单，与锁文件一致；锁文件负责传递依赖，不进 manifest）。
    """
    package_json = json.loads((WEB_DIR / "package.json").read_text(encoding="utf-8"))
    result: dict[str, dict[str, str]] = {}
    for kind in ("dependencies", "devDependencies"):
        for name, version in package_json.get(kind, {}).items():
            result[name] = {"version": version, "kind": kind}
    return result


def read_backend_deps() -> dict[str, dict[str, str]]:
    """读后端直接依赖（requirements.txt + requirements-dev.txt，含 requirements-dev 里的 -r 展开）。

    返回 {包名: {"version": 精确版本, "kind": "runtime"|"dev"}}。
    """
    result: dict[str, dict[str, str]] = {}

    def parse(path: Path, kind: str) -> None:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()  # 去注释
            if line == "" or line.startswith("-"):
                continue  # 跳过 -r/--requirement 等选项行
            match = re.match(r"^([A-Za-z0-9._-]+)(\[[^\]]+\])?==(.+)$", line)
            if match is None:
                print(f"[t01] 警告：无法解析依赖行：{line}（{path.name}）", file=sys.stderr)
                continue
            result[match.group(1)] = {"version": match.group(3).strip(), "kind": kind}

    parse(SERVER_DIR / "requirements-dev.txt", "dev")
    parse(SERVER_DIR / "requirements.txt", "runtime")  # runtime 后写，覆盖 dev 里的同名列
    return result


# ---- 许可元数据读取（前端）-------------------------------------------------------


def frontend_license_info(package: str) -> dict[str, Any]:
    """从前端包元数据读许可。

    读取 `web/node_modules/<pkg>/package.json` 的 `license`/`licenses` 字段，
    并探测包内许可文本文件（LICENSE / LICENSE.md / COPYING 等）作为锚点。
    """
    pkg_dir = WEB_NODE_MODULES / package
    pkg_json = pkg_dir / "package.json"
    if not pkg_json.exists():
        return {"spdx": PLACEHOLDER, "evidence_anchor": f"file:web/node_modules/{package}（未安装）"}

    meta = json.loads(pkg_json.read_text(encoding="utf-8"))
    spdx = meta.get("license")
    if spdx is None and isinstance(meta.get("licenses"), list):
        # 旧式 licenses 数组（如 [{ "type": "MIT" }]）
        spdx = " OR ".join(item.get("type", "?") for item in meta["licenses"] if isinstance(item, dict))
    spdx = spdx if isinstance(spdx, str) and spdx.strip() else PLACEHOLDER

    license_file = ""
    for candidate in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING", "LICENSE-MIT"):
        if (pkg_dir / candidate).exists():
            license_file = candidate
            break
    # 锚点写**完整可定位**的相对路径（不省略中间段），保证能从仓库直接找到证据文件
    anchor = f"file:web/node_modules/{package}/{license_file or 'package.json'}"
    return {"spdx": spdx, "evidence_anchor": anchor}


def frontend_attribution_terms(package: str) -> list[str]:
    """探测需要额外记录的条款（包内含 NOTICE / 第三方声明时为人工提示）。

    这里只做**机械提示**，不自动判定——许可结论由人工确认后写进 manifest（锚点纪律）。
    """
    pkg_dir = WEB_NODE_MODULES / package
    for candidate in NOTICE_CANDIDATES:
        if (pkg_dir / candidate).exists():
            return [f"含 {candidate}（第三方声明）：分发时须一并保留，人工复核见 T01 记录"]
    return []


# ---- 许可元数据读取（后端）-------------------------------------------------------


def iter_backend_dist_infos() -> list[Path]:
    """列出后端虚拟环境里的 *.dist-info 目录（兼容 Windows 与 POSIX 两种布局）。"""
    if SERVER_VENV_SITE.exists():
        return sorted(SERVER_VENV_SITE.glob("*.dist-info"))
    posix_root = SERVER_VENV_SITE_POSIX
    if posix_root.exists():
        return sorted(posix_root.glob("python*/site-packages/*.dist-info"))
    return []


def parse_metadata(dist_info: Path) -> dict[str, str]:
    """解析 dist-info/METADATA 的头部字段（RFC822 风格，遇空行结束头部）。"""
    fields: dict[str, list[str]] = {}
    for line in (dist_info / "METADATA").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip() == "":
            break
        if ": " in line:
            key, _, value = line.partition(": ")
            fields.setdefault(key.strip(), []).append(value.strip())
    return {key: " | ".join(values) for key, values in fields.items()}


def _dist_info_relative(dist_info: Path) -> str:
    """把 dist-info 目录转成相对仓库根的 POSIX 风格相对路径（Windows / Linux 通用）。"""
    try:
        return dist_info.relative_to(REPO_ROOT).as_posix()
    except ValueError:  # pragma: no cover - 仅当 venv 不在仓库内时发生
        return dist_info.as_posix()


def backend_license_info(package: str) -> dict[str, Any]:
    """从后端包元数据读许可：优先 PEP 639 的 License-Expression，其次 License，最后 Classifier。"""
    target = normalize(package)
    for dist_info in iter_backend_dist_infos():
        if normalize(dist_info.name.split("-")[0]) == target:
            meta = parse_metadata(dist_info)
            spdx = meta.get("License-Expression") or meta.get("License") or ""
            if not spdx:
                classifiers = [
                    part.split("::")[-1].strip()
                    for part in meta.get("Classifier", "").split(" | ")
                    if part.strip().startswith("License ::") and part.strip().count("::") == 3
                ]
                # 只接受形如 `License :: OSI Approved :: MIT License` 的**完整分类**（层级数不足的是类目节点）
                spdx = " / ".join(classifiers) if classifiers else ""
            license_file = ""
            for candidate in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
                if (dist_info / candidate).exists():
                    license_file = candidate
                    break
            # PEP 639 起许可文本放在 dist-info/licenses/ 子目录下：优先定位到具体的 LICENSE 文件，
            # 找不到具体文件才退回目录（目录锚点仍可读，但定位精度低）
            if not license_file and (dist_info / "licenses").is_dir():
                for child in sorted((dist_info / "licenses").iterdir()):
                    if child.is_file() and child.name.upper().startswith(("LICENSE", "COPYING")):
                        license_file = f"licenses/{child.name}"
                        break
                else:
                    license_file = "licenses/"
            anchor = f"file:{_dist_info_relative(dist_info)}/{license_file or 'METADATA'}"
            return {"spdx": spdx, "evidence_anchor": anchor}
    return {"spdx": "", "evidence_anchor": f"file:server/.venv（未找到 {package} 的元数据）"}


def backend_attribution_terms(package: str) -> list[str]:
    """后端同理：包内带 NOTICE / 第三方声明的一律提示人工复核。"""
    target = normalize(package)
    for dist_info in iter_backend_dist_infos():
        if normalize(dist_info.name.split("-")[0]) == target:
            for candidate in NOTICE_CANDIDATES:
                if (dist_info / candidate).exists():
                    return [f"含 {candidate}（第三方声明）：分发时须一并保留，人工复核见 T01 记录"]
    return []


# ---- manifest 生成 ---------------------------------------------------------------


def load_manifest() -> list[dict[str, Any]]:
    """读现有 manifest；不存在则返回空列表（首次生成用）。"""
    if not MANIFEST_PATH.exists():
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("licenses/manifest.json 顶层必须是数组")
    return data


def new_entry(
    *,
    package: str,
    version: str,
    scope: str,
    license_info: dict[str, Any],
    additional_terms: list[str],
    serves_online: bool,
    distribution: list[str],
) -> dict[str, Any]:
    """构造一个新 manifest 条目（未在 manifest 中出现过的包）。"""
    today = date.today().isoformat()
    return {
        "id": package,
        "name": package,
        "version": version,
        "scope": scope,  # 预算桶（03 §5.2）：frontend / backend / tool
        "layer": {
            "code": {"spdx": license_info["spdx"], "evidence": {"anchor": license_info["evidence_anchor"], "read_at": today}},
            "weights": None,  # ② 模型权重层：本阶段无模型依赖
            "additional_terms": additional_terms,  # ③ 附加条款
        },
        "attribution": {
            # 是否强制署名由人工确认后填写；生成阶段先按 false 起步（MIT/BSD/Apache 系不强制"显著署名"）
            "required": False,
            "template": None,
        },
        "serves_online": serves_online,
        "distribution": distribution,
        "introduced_at": today,
        "reviewed_at": today,
        "owner": DEFAULT_OWNER,
    }


def _merge_terms(detected: list[str], existing: list[str]) -> list[str]:
    """合并"本次探测到的条款"与"manifest 里已有人工条款"：

    两个来源都要保留——探测值负责"新发现"（如包内新增 NOTICE），
    人工值负责"文档化的结论"（如 LGPL 的随附义务说明），后者不能被生成脚本冲掉。
    """
    merged = list(detected)
    for item in existing:
        if item not in merged:
            merged.append(item)
    return merged


def _update_existing(
    template: dict[str, Any],
    *,
    version: str,
    lic: dict[str, Any],
    terms: list[str],
    today: str,
) -> dict[str, Any]:
    """更新一条已有条目：只刷新版本与许可证据，其他人工字段原样保留。"""
    entry = dict(template)
    entry["version"] = version
    old_layer = template.get("layer", {})
    old_code = old_layer.get("code", {})
    entry["layer"] = {
        **old_layer,
        "code": {
            # resolve_spdx：元数据不是合法 SPDX 时保留人工核实值（防覆盖）
            "spdx": resolve_spdx(lic["spdx"], old_code.get("spdx")),
            "evidence": {"anchor": lic["evidence_anchor"], "read_at": today},
        },
        "additional_terms": _merge_terms(terms, old_layer.get("additional_terms") or []),
    }
    entry["reviewed_at"] = today
    return entry


def generate() -> int:
    """生成/更新 manifest：已有条目保留人工字段，只刷新版本与许可元数据。"""
    frontend = read_frontend_deps()
    backend = read_backend_deps()
    # 用归一化包名索引已有条目，避免 `Django` / `django` 这类大小写差异导致重复新增
    existing = {normalize(entry["id"]): entry for entry in load_manifest()}
    tool_names = {normalize(name) for name in TOOL_PACKAGES}
    today = date.today().isoformat()
    entries: list[dict[str, Any]] = []

    for package, info in frontend.items():
        lic = frontend_license_info(package)
        terms = frontend_attribution_terms(package)
        template = existing.get(normalize(package))
        if template is not None:
            entry = _update_existing(template, version=info["version"], lic=lic, terms=terms, today=today)
        else:
            entry = new_entry(
                package=package,
                version=info["version"],
                scope="tool" if normalize(package) in tool_names else "frontend",
                license_info={"spdx": resolve_spdx(lic["spdx"], None), "evidence_anchor": lic["evidence_anchor"]},
                additional_terms=terms,
                # 构建产物会进对外服务的包标 true；纯开发工具标 false
                serves_online=info["kind"] == "dependencies",
                distribution=["npm"],
            )
        entries.append(entry)

    for package, info in backend.items():
        lic = backend_license_info(package)
        terms = backend_attribution_terms(package)
        template = existing.get(normalize(package))
        if template is not None:
            entry = _update_existing(template, version=info["version"], lic=lic, terms=terms, today=today)
        else:
            entry = new_entry(
                package=package,
                version=info["version"],
                scope="tool" if normalize(package) in tool_names else "backend",
                license_info={"spdx": resolve_spdx(lic["spdx"], None), "evidence_anchor": lic["evidence_anchor"]},
                additional_terms=terms,
                serves_online=info["kind"] == "runtime",
                distribution=["pip"],
            )
        entries.append(entry)

    # 排序：先按 scope（frontend → backend → tool），再按包名，保证生成结果稳定可比对
    scope_order = {"frontend": 0, "backend": 1, "tool": 2}
    entries.sort(key=lambda e: (scope_order.get(e.get("scope", "tool"), 9), e["id"].lower()))

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[t01] 已写入 {MANIFEST_PATH.relative_to(REPO_ROOT)}：{len(entries)} 个条目")

    # 对账提示：清单里存在但已不在依赖中的条目（不自动删除，需人工确认）
    current_ids = {normalize(p) for p in {*frontend, *backend}}
    stale = [entry["id"] for entry in entries if normalize(entry["id"]) not in current_ids]
    if stale:
        print(f"[t01] 注意：以下条目已不在直接依赖中，请人工确认是否移除：{stale}", file=sys.stderr)
    return 0


# ---- 校验（闸 2）-----------------------------------------------------------------


REQUIRED_FIELDS = ("id", "name", "version", "scope", "layer", "attribution", "serves_online", "distribution", "introduced_at", "reviewed_at", "owner")


def check_entries() -> list[str]:
    """执行全部机械判据，返回失败原因列表（空列表 = 全绿）。"""
    failures: list[str] = []
    entries = load_manifest()
    if not entries:
        return ["manifest 为空或不存在：先运行 --generate"]

    # ---- 判据 1：清单一致性（manifest ↔ 实际直接依赖，双向）----
    declared = {normalize(entry["id"]) for entry in entries}
    actual = {normalize(p) for p in read_frontend_deps()} | {normalize(p) for p in read_backend_deps()}
    missing_in_manifest = sorted(actual - declared)
    extra_in_manifest = sorted(declared - actual)
    if missing_in_manifest:
        failures.append(f"清单不一致：以下直接依赖未登记进 manifest：{missing_in_manifest}")
    if extra_in_manifest:
        failures.append(f"清单不一致：以下 manifest 条目已不是直接依赖（需人工确认后移除）：{extra_in_manifest}")

    # ---- 判据 2：三层许可字段完整性 + 占位符拦截 ----
    for entry in entries:
        eid = entry.get("id", "<无 id>")
        for field in REQUIRED_FIELDS:
            if field not in entry:
                failures.append(f"[{eid}] 缺字段：{field}")
        layer = entry.get("layer", {})
        for key in ("code", "weights", "additional_terms"):
            if key not in layer:
                failures.append(f"[{eid}] 缺 layer.{key}（三层许可必须逐层表态，不适用也要显式写 null）")
        code = layer.get("code", {})
        spdx = code.get("spdx", "")
        if not spdx or PLACEHOLDER in str(spdx):
            failures.append(f"[{eid}] layer.code.spdx 缺失或为占位符（需人工核实上游许可原文）")
        evidence = code.get("evidence", {})
        if not evidence.get("anchor") or PLACEHOLDER in str(evidence.get("anchor", "")):
            failures.append(f"[{eid}] layer.code.evidence.anchor 缺失或为占位符")
        if not evidence.get("read_at"):
            failures.append(f"[{eid}] layer.code.evidence.read_at 缺失")

    # ---- 判据 b / c：强制署名条目的模板与公开文档同句文案 ----
    # 两条件合并处理：template 缺失时只能报判据 b，不能再让判据 c 去取模板（否则是异常而非失败项）
    notices_text = NOTICES_PATH.read_text(encoding="utf-8") if NOTICES_PATH.exists() else None
    if notices_text is None:
        failures.append("THIRD-PARTY-NOTICES.md 不存在：先运行 --notices")
    for entry in entries:
        if entry.get("attribution", {}).get("required") is not True:
            continue
        template = entry["attribution"].get("template")
        if not isinstance(template, dict):
            failures.append(f"[{entry['id']}] attribution.required=true 但缺少 template（判据 b）")
            continue
        for field in ("component", "usage", "url"):
            value = template.get(field, "")
            if not value or PLACEHOLDER in str(value):
                failures.append(f"[{entry['id']}] 署名模板缺 {field}（判据 b）")
        if notices_text is not None:
            sentence = attribution_sentence(entry)
            if sentence not in notices_text:
                failures.append(f"[{entry['id']}] 公开文档缺同句署名文案（判据 c）：{sentence}")

    # ---- 判据 1 附加：THIRD-PARTY-NOTICES.md 与 manifest 全量一致（防止文档漂移）----
    if notices_text is not None:
        for entry in entries:
            if entry["id"] not in notices_text:
                failures.append(f"[{entry['id']}] 未出现在 THIRD-PARTY-NOTICES.md 中（文档漂移）")
    return failures


def attribution_sentence(entry: dict[str, Any]) -> str:
    """由模板拼出**同句**署名文案（判据 b/c/d 三处必须用同一函数，防止文案漂移）。"""
    template = entry["attribution"]["template"]
    return f"{template['component']}（{template['usage']}）—— {template['url']}"


# ---- 许可文本独立裁判（元数据声明 vs 上游 LICENSE 正文）----------------------------
#
# 为什么需要：`layer.code.spdx` 取自包元数据的**声明**，而声明可能过时、写错或是自由文本。
# 上游 LICENSE 文件正文是**独立于声明**的第二条路径（项目纪律：差分优先，差异逐条归因）。
# 本判据不与声明一致 → 差异即失败，必须人工归因后修正 manifest。


def read_license_text(anchor: str) -> str:
    """读取锚点指向的证据文件；锚点是目录时拼接其中所有候选文本文件。

    路径基准用模块级 `REPO_ROOT`（而非写死仓库根），便于注入测试重定向到假仓库。
    """
    rel = anchor.removeprefix("file:")
    path = REPO_ROOT / rel
    if path.is_dir():
        texts = [
            child.read_text(encoding="utf-8", errors="replace")
            for child in sorted(path.rglob("*"))
            if child.is_file() and child.suffix.lower() in {"", ".txt", ".md", ".rst"}
        ]
        return "\n".join(texts)
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def detect_license_families(text: str) -> list[str]:
    """从许可正文里识别许可族（可识别多重文本，返回识别到的全部）。

    识别用的是各许可的**特征句**，不是全文比对——同一许可的年份/作者会变，特征句不变。
    """
    low = text.lower()
    found: list[str] = []
    if "permission is hereby granted, free of charge" in low:
        found.append("MIT")
    if "permission to use, copy, modify, and/or distribute this software" in low:
        found.append("ISC")
    if "apache license" in low and "version 2.0" in low:
        found.append("Apache-2.0")
    if "mozilla public license version 2.0" in low:
        found.append("MPL-2.0")
    has_bsd_core = "redistribution and use in source and binary forms" in low
    # BSD-3 的第三条款有两种常见合法措辞：
    #   ① "Neither the name of X nor the names of its contributors may be used to endorse or promote..."
    #   ② "The names of its contributors may not be used to endorse or promote..."
    # 二者共同特征是 "endorse or promote" + "specific prior written permission"。
    # （此处曾把 pytest-django 误判为 BSD-2——差分归因记录见 T01 报告「检测器局限修正」。）
    bsd3_marker = "neither the name" in low or (
        "endorse or promote" in low and "specific prior written permission" in low
    )
    if has_bsd_core and bsd3_marker:
        found.append("BSD-3-Clause")
    elif has_bsd_core:
        found.append("BSD-2-Clause")
    if "gnu lesser general public license" in low:
        # 记录版本，便于与 `LGPL-3.0-only` 这类带版本号的值对账
        found.append("LGPL-3.0" if "version 3" in low else "LGPL")
    elif "gnu general public license" in low and "version 3" in low:
        found.append("GPL-3.0")
    return found


def spdx_matches_text(declared: str, families: list[str]) -> bool:
    """判断 manifest 声明的 SPDX 与正文识别结果是否一致（容忍 `-only` / `-or-later` 后缀）。"""

    def strip_suffix(value: str) -> str:
        return value.replace("-only", "").replace("-or-later", "").strip()

    declared_base = strip_suffix(declared.split()[0])  # 只取表达式首项（`A AND B` 的完整判定超出本脚本范围）
    for family in families:
        family_base = strip_suffix(family)
        if declared_base == family_base or declared_base.startswith(family_base):
            return True
    return False


def verify_license_texts(*, verbose: bool) -> list[str]:
    """逐条用上游许可正文核对 manifest 的 SPDX 声明，返回不一致清单（空 = 全一致）。"""
    mismatches: list[str] = []
    unreadable: list[str] = []
    for entry in load_manifest():
        declared = entry["layer"]["code"]["spdx"]
        anchor = entry["layer"]["code"]["evidence"]["anchor"]
        text = read_license_text(anchor)
        if not text.strip():
            unreadable.append(f"[{entry['id']}] 许可正文读不到（锚点：{anchor}）")
            continue
        families = detect_license_families(text)
        if not families:
            unreadable.append(f"[{entry['id']}] 正文无法识别许可族（需人工看：{anchor}）")
            continue
        ok = spdx_matches_text(declared, families)
        if verbose:
            mark = "[OK]" if ok else "[X] "
            print(f"  {mark} {entry['id']:28s} 声明={declared:16s} 正文识别={','.join(families)}")
        if not ok:
            mismatches.append(
                f"[{entry['id']}] 声明 {declared} 与许可正文识别结果（{','.join(families)}）不一致——需人工归因（我方登记错 / 元数据过时 / 版本漂移）"
            )
    for item in unreadable:
        # 读不到 ≠ 不一致：无法差分的条目必须**显式声明**（不得默认跳过）
        print(f"  [!]  {item}（无独立裁判，需人工核对）", file=sys.stderr)
    return mismatches


def check() -> int:
    failures = check_entries()
    failures += verify_license_texts(verbose=False)
    if failures:
        print("[t01] 校验失败：", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("[t01] 校验通过：清单一致、三层许可字段完整、判据 b/c 满足、许可正文与声明一致")
    return 0


# ---- 生成 THIRD-PARTY-NOTICES.md（落点 ②）---------------------------------------


def render_notices() -> int:
    entries = load_manifest()
    lines = [
        "# 第三方组件与许可（THIRD-PARTY-NOTICES）",
        "",
        "> 本文件由 `tools/license-manifest/t01_licenses.py --notices` 从 `licenses/manifest.json` 生成，**请勿手工编辑**。",
        "> 任何许可结论的变更必须改 manifest（唯一真源），再重新生成本文件。",
        "",
        "本项目使用了以下第三方开源组件，在此致谢并逐条列出许可信息。",
        "",
    ]
    # 强制署名条目单独置顶（判据 c 的同句文案就在这一段）
    required = [e for e in entries if e.get("attribution", {}).get("required") is True]
    if required:
        lines += ["## 须显著署名的组件", ""]
        for entry in required:
            lines.append(f"- {attribution_sentence(entry)}")
        lines.append("")
    lines += ["## 全部组件清单", "", "| 组件 | 版本 | 许可（SPDX） | 用途面 | 附加条款 |", "|---|---|---|---|---|"]
    for entry in sorted(entries, key=lambda e: e["id"].lower()):
        spdx = entry["layer"]["code"]["spdx"]
        terms = "；".join(entry["layer"]["additional_terms"]) or "—"
        online = "对外服务链路" if entry["serves_online"] else "仅开发/构建"
        lines.append(f"| {entry['name']} | {entry['version']} | {spdx} | {online} | {terms} |")
    lines += [
        "",
        "## 许可原文与证据锚点",
        "",
        "每个组件的许可原文位置（供复核）记录在 `licenses/manifest.json` 的 `layer.code.evidence.anchor` 字段；",
        "复核周期与责任人见 manifest 的 `reviewed_at` / `owner`。",
        "",
        "## 生成信息",
        "",
        f"- 生成日期：{date.today().isoformat()}",
        f"- 数据来源：`licenses/manifest.json`（{len(entries)} 个条目）",
        "",
    ]
    NOTICES_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[t01] 已写入 {NOTICES_PATH.relative_to(REPO_ROOT)}")
    return 0


# ---- 闸 3：构建期署名断言（判据 d）-----------------------------------------------


def check_build(dist_dir: Path) -> int:
    """扫描构建产物，确认每个"强制署名"条目的文案都出现在产物中。

    这是防线而不是仪式：构造 `attribution.required = true` 但不渲染署名的假组件时，
    本检查必须返回非零（见同目录 test_t01_injections.py 的注入用例）。
    """
    entries = load_manifest()
    required = [e for e in entries if e.get("attribution", {}).get("required") is True]
    if not dist_dir.exists():
        print(f"[t01] 构建目录不存在：{dist_dir}", file=sys.stderr)
        return 1
    if not required:
        print("[t01] 当前 manifest 无强制署名条目 → 闸 3 为占位（真断言随首个 required 条目启用）")
        return 0

    blobs = {
        path: path.read_text(encoding="utf-8", errors="replace")
        for path in dist_dir.rglob("*")
        if path.is_file() and path.suffix in {".html", ".js", ".mjs", ".css"}
    }
    failures = []
    for entry in required:
        sentence = attribution_sentence(entry)
        if not any(sentence in text for text in blobs.values()):
            failures.append(f"[{entry['id']}] 构建产物中找不到署名文案（判据 d）：{sentence}")
    if failures:
        print("[t01] 构建期署名断言失败：", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"[t01] 构建期署名断言通过：{len(required)} 个强制署名条目均在产物中找到")
    return 0


# ---- 预算桶统计（docs/plan/03 §5.2）----------------------------------------------


def report_budget() -> int:
    entries = load_manifest()
    buckets: dict[str, list[str]] = {"frontend": [], "backend": [], "tool": []}
    for entry in entries:
        buckets.setdefault(entry.get("scope", "tool"), []).append(entry["id"])
    caps = {"frontend": 18, "backend": 18, "tool": 12}
    total = sum(len(v) for v in buckets.values())
    print(f"[t01] 直接依赖总数：{total} / 48")
    for name, cap in caps.items():
        members = sorted(buckets.get(name, []))
        flag = "[OK]" if len(members) <= cap else "[超预算] 第 N 个依赖 = 架构事件，需登记理由"
        print(f"  - {name:9s} {len(members):2d} / {cap} {flag}")
    if total > 48:
        print("[t01] [超预算] 总数超 48：按 03 §5.2 必须回表登记并说明理由", file=sys.stderr)
        return 1
    return 0


# ---- 命令行入口 ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="许可登记与生成脚本（唯一真源：licenses/manifest.json）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="从依赖元数据生成/更新 manifest 草稿")
    group.add_argument("--check", action="store_true", help="校验（CI 闸 2）")
    group.add_argument("--notices", action="store_true", help="由 manifest 生成 THIRD-PARTY-NOTICES.md")
    group.add_argument("--check-build", metavar="DIST", help="构建产物署名断言（闸 3，判据 d）")
    group.add_argument("--verify-text", action="store_true", help="用上游许可正文核对 SPDX 声明（独立裁判）")
    group.add_argument("--budget", action="store_true", help="按 scope 统计依赖预算桶")
    args = parser.parse_args(argv)

    if args.generate:
        return generate()
    if args.check:
        return check()
    if args.notices:
        return render_notices()
    if args.check_build:
        return check_build(Path(args.check_build))
    if args.verify_text:
        print("[t01] 许可正文独立裁判（声明 vs 上游 LICENSE 正文）：")
        mismatches = verify_license_texts(verbose=True)
        if mismatches:
            print("[t01] 存在不一致：", file=sys.stderr)
            for item in mismatches:
                print(f"  - {item}", file=sys.stderr)
            return 1
        print("[t01] 全部条目声明与正文一致")
        return 0
    if args.budget:
        return report_budget()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
