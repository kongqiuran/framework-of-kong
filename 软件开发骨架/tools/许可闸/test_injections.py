"""注入用例：证明许可闸**真的会红**（不是空转）——骨架版。

通用化自 learning-os 的 `tools/license-manifest/test_t01_injections.py`（仅改了文件头与运行说明）。

设计要点（可直接搬到任何防线）：
1. **每道防线配一个破坏用例**：注入后必须返回非零；返回 0 的防线就是装饰品；
2. **同时配对照组**：基线全一致时必须通过——防止写出一条“永远红”的假防线；
3. **不碰真实仓库**：全部在 pytest 的 tmp_path 里构造假项目，
   通过 monkeypatch 重定向被测算脚本的路径常量（脚本自身代码不动）。

运行：`<venv>/python -m pytest test_injections.py -q`（需 pytest）。

对应 docs/plan/03 §6.4「注入用例」与任务清单 §3.2 的**红过计划**：
每条防线被故意破坏一次，期望对应的检查返回**非零**。若某条注入下检查仍然通过，
说明那条防线是装饰品——本文件的用例就是把它抓出来。

运行方式（用后端虚拟环境的 pytest）：

    server/.venv/Scripts/python.exe -m pytest tools/license-manifest/test_t01_injections.py -q

本文件**不改仓库真实文件**：所有注入都在 pytest 的 tmp_path 里构造假仓库，
通过 monkeypatch 把脚本的路径常量重定向过去。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

TOOL_PATH = Path(__file__).with_name("t01_licenses.py")

# 与假仓库配套的合规条目（注入用例在此基线上做单点破坏）
MIT_TEXT = "Permission is hereby granted, free of charge, to any person obtaining a copy."


def load_tool() -> ModuleType:
    """按文件路径加载 T-01 脚本（目录名含连字符，不能作为包 import）。"""
    spec = importlib.util.spec_from_file_location("t01_licenses", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    """构造最小假仓库：1 个前端直接依赖（real-pkg，MIT），后端无依赖。"""
    tool = load_tool()

    web = tmp_path / "web"
    pkg_dir = web / "node_modules" / "real-pkg"
    pkg_dir.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps({"dependencies": {"real-pkg": "1.0.0"}}, ensure_ascii=False), encoding="utf-8"
    )
    (pkg_dir / "package.json").write_text(
        json.dumps({"name": "real-pkg", "version": "1.0.0", "license": "MIT"}), encoding="utf-8"
    )
    (pkg_dir / "LICENSE").write_text(MIT_TEXT, encoding="utf-8")

    server = tmp_path / "server"
    server.mkdir()
    (server / "requirements.txt").write_text("", encoding="utf-8")
    (server / "requirements-dev.txt").write_text("", encoding="utf-8")

    licenses_dir = tmp_path / "licenses"
    licenses_dir.mkdir()

    # 把脚本的路径常量指向假仓库（脚本自身代码不动）
    monkeypatch.setattr(tool, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(tool, "WEB_DIR", web)
    monkeypatch.setattr(tool, "WEB_NODE_MODULES", web / "node_modules")
    monkeypatch.setattr(tool, "SERVER_DIR", server)
    monkeypatch.setattr(tool, "MANIFEST_PATH", licenses_dir / "manifest.json")
    monkeypatch.setattr(tool, "NOTICES_PATH", tmp_path / "THIRD-PARTY-NOTICES.md")
    # 默认写一份含 `real-pkg` 的公开文档；需要测"文档缺句"的用例自己覆盖它
    (tmp_path / "THIRD-PARTY-NOTICES.md").write_text(
        "# 第三方组件与许可\n\nreal-pkg\n", encoding="utf-8"
    )
    return tool, tmp_path


def valid_entry(sentence: str | None = None) -> dict:
    """一条字段完整、声明与正文一致的条目（可选：带强制署名模板）。"""
    attribution: dict = {"required": False, "template": None}
    if sentence is not None:
        attribution = {
            "required": True,
            "template": {"component": "real-pkg", "usage": "解析", "url": "https://example.com/real-pkg"},
        }
    return {
        "id": "real-pkg",
        "name": "real-pkg",
        "version": "1.0.0",
        "scope": "frontend",
        "layer": {
            "code": {
                "spdx": "MIT",
                "evidence": {"anchor": "file:web/node_modules/real-pkg/LICENSE", "read_at": "2026-10-07"},
            },
            "weights": None,
            "additional_terms": [],
        },
        "attribution": attribution,
        "serves_online": True,
        "distribution": ["npm"],
        "introduced_at": "2026-10-07",
        "reviewed_at": "2026-10-07",
        "owner": "待指派",
    }


def write_manifest(tool: ModuleType, entries: list[dict]) -> None:
    tool.MANIFEST_PATH.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def write_notices(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


# ---- 对照组：全一致时必须通过（防止"永远红"的假防线）------------------------------


def test_baseline_passes(fake_repo: tuple[ModuleType, Path]) -> None:
    """基线：清单一致 + 三层字段完整 + 无强制署名条目 → check_entries 必须为空。"""
    tool, _ = fake_repo
    write_manifest(tool, [valid_entry()])
    assert tool.check_entries() == []


# ---- 注入 2：新增依赖但不登记 manifest → 清单不一致 -------------------------------


def test_injection_new_dependency_not_registered(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：真实依赖 real-pkg 未登记（manifest 里只有别的包）→ --check 必须失败。"""
    tool, _ = fake_repo
    other = valid_entry()
    other["id"] = "other-pkg"
    other["name"] = "other-pkg"
    write_manifest(tool, [other])
    failures = tool.check_entries()
    assert any("未登记" in item and "real-pkg" in item for item in failures), failures


def test_injection_stale_manifest_entry(fake_repo: tuple[ModuleType, Path]) -> None:
    """反向注入：manifest 里有依赖清单中已不存在的条目 → 同样必须失败。"""
    tool, _ = fake_repo
    ghost = valid_entry()
    ghost["id"] = "ghost-pkg"
    write_manifest(tool, [valid_entry(), ghost])
    failures = tool.check_entries()
    assert any("已不是直接依赖" in item for item in failures), failures


# ---- 注入：三层许可字段与占位符 ---------------------------------------------------


def test_injection_missing_layer_weights(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：条目缺 layer.weights（三层许可缺一层）→ 必须失败。"""
    tool, _ = fake_repo
    entry = valid_entry()
    del entry["layer"]["weights"]
    write_manifest(tool, [entry])
    failures = tool.check_entries()
    assert any("layer.weights" in item for item in failures), failures


def test_injection_placeholder_spdx(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：spdx 仍是占位符（未人工核实）→ 必须失败。"""
    tool, _ = fake_repo
    entry = valid_entry()
    entry["layer"]["code"]["spdx"] = tool.PLACEHOLDER
    write_manifest(tool, [entry])
    failures = tool.check_entries()
    assert any("spdx" in item and "占位符" in item for item in failures), failures


# ---- 注入 1 / 4：强制署名条目的模板与文案（判据 b / c / d）------------------------


def test_injection_required_but_template_missing(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：required=true 但 template=null（判据 b）→ 必须失败且**不得抛异常**。"""
    tool, _ = fake_repo
    entry = valid_entry()
    entry["attribution"] = {"required": True, "template": None}
    write_manifest(tool, [entry])
    failures = tool.check_entries()
    assert any("缺少 template" in item for item in failures), failures


def test_injection_notices_missing_sentence(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：模板齐全但公开文档里没有同句署名（判据 c）→ 必须失败。"""
    tool, _ = fake_repo
    entry = valid_entry(sentence="yes")
    write_manifest(tool, [entry])
    write_notices(tool.NOTICES_PATH, "# 第三方组件\n\n（这里故意没有署名句）\n")
    failures = tool.check_entries()
    assert any("判据 c" in item for item in failures), failures


def test_injection_build_missing_sentence(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：构建产物里找不到署名文案（闸 3 / 判据 d）→ check_build 必须返回非零。"""
    tool, _ = fake_repo
    entry = valid_entry(sentence="yes")
    write_manifest(tool, [entry])
    dist = tool.MANIFEST_PATH.parent.parent / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>没有任何署名文案</html>", encoding="utf-8")

    assert tool.check_build(dist) == 1


def test_build_passes_when_sentence_present(fake_repo: tuple[ModuleType, Path]) -> None:
    """对照组：产物里含同句署名 → check_build 返回 0（证明闸 3 不是永远红）。"""
    tool, _ = fake_repo
    entry = valid_entry(sentence="yes")
    write_manifest(tool, [entry])
    dist = tool.MANIFEST_PATH.parent.parent / "dist"
    dist.mkdir()
    sentence = tool.attribution_sentence(entry)
    (dist / "index.html").write_text(f"<html><footer>{sentence}</footer></html>", encoding="utf-8")

    assert tool.check_build(dist) == 0


# ---- 独立裁判：许可正文与声明不一致 -------------------------------------------------


def test_injection_license_text_mismatch(fake_repo: tuple[ModuleType, Path]) -> None:
    """注入：声明 BSD-3-Clause，但正文是 MIT → 独立裁判必须报不一致。"""
    tool, _ = fake_repo
    entry = valid_entry()
    entry["layer"]["code"]["spdx"] = "BSD-3-Clause"  # 与 real-pkg/LICENSE（MIT）不符
    write_manifest(tool, [entry])
    mismatches = tool.verify_license_texts(verbose=False)
    assert len(mismatches) == 1 and "BSD-3-Clause" in mismatches[0], mismatches


def test_license_text_match_passes(fake_repo: tuple[ModuleType, Path]) -> None:
    """对照组：声明 MIT、正文 MIT → 独立裁判无差异。"""
    tool, _ = fake_repo
    write_manifest(tool, [valid_entry()])
    assert tool.verify_license_texts(verbose=False) == []
