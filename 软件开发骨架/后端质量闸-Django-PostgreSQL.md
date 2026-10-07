---
tags: [骨架, 后端, 质量闸, Django, PostgreSQL, Docker, Compose]
date: 2026-10-07
source: learning-os V4 `T01` 实测（容器 ＋ 本机双路径验证）
---

# 骨架：后端质量闸（Django + PostgreSQL + Compose）

> 适用于：Python 后端新项目起步。
> 目标：**配置不硬编码、坏配置拒绝启动、四道检查跑通**，然后才写业务。

---

## 1. 框架与版本选择

| 项 | 选择 | 理由 |
|---|---|---|
| 框架 | **Django LTS**（本文成文时 5.2.18，支持至 2028-04） | LTS 提供 3 年安全支持，是少数给出明确支持窗口的框架；升级只跟随 LTS，不追 feature 线 |
| 数据库 | **PostgreSQL**（镜像 `postgres:17`） | 写密集 / 多进程 / fork 场景下 SQLite 是官方列明的禁区；PG 走容器可避免本机安装客户端 |
| 接口层 | 先**纯 Django**（`JsonResponse` + 版本前缀路由） | 引入 DRF 等包级实现前先做依赖考古与预算记账；**待定 ≠ 不能用，是"先记账再引入"** |

## 2. 配置纪律（最重要的一节）

> 三原则：**不硬编码环境相关值**；**开发默认值可用但不安全**；**坏配置拒绝启动而不是静默降级**。

```python
DEBUG = env_bool("DJANGO_DEBUG", default=False)          # 默认关：安全的默认值

_secret = env("DJANGO_SECRET_KEY")
if _secret is None:
    if DEBUG:
        _secret = "dev-insecure-placeholder-key-do-not-use-outside-local-development"
    else:
        raise ImproperlyConfigured(         # 非开发态缺密钥 → 直接拒绝启动
            "缺少 DJANGO_SECRET_KEY：非开发环境必须通过环境变量提供。参见 .env.example"
        )
SECRET_KEY = _secret
```

配套约定：

- `env()` 把**空字符串当未设置**（否则 `.env` 里写 `X=` 会被当成有效值）；
- `.env` **不入库**，仓库只提交 `.env.example`（含占位值与生成随机密钥的命令）；
- 配置项分两批：**当前被代码消费的**写进 `.env.example`，**尚未消费的**只在文档里登记
  —— 避免"看起来配了其实没人读"；
- 上传体积这类**多层同值**的配置（nginx / 框架 / 磁盘配额）指向**同一个环境变量**，避免改一处漏一处。

## 3. 容器编排要点（`compose.dev.yml`）

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-learning_os}
      POSTGRES_USER: ${POSTGRES_USER:-learning_os}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-learning_os_dev_only}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-learning_os} -d ${POSTGRES_DB:-learning_os}"]
      interval: 5s
      timeout: 5s
      retries: 12
      start_period: 10s
  web:
    build: { context: ./server }
    env_file: [.env]
    environment:
      POSTGRES_HOST: db      # 关键：覆盖 .env 里给"本机直跑"用的 localhost
    depends_on:
      db: { condition: service_healthy }   # 等数据库真的可连，不是"容器起来了"
```

要点：
- **healthcheck + `condition: service_healthy`**：容器 running ≠ 数据库可连；
- **`POSTGRES_HOST` 在容器内必须覆盖为服务名**（同一个 `.env` 同时服务"本机直跑"与"容器内"两种形态）；
- 源码用 volume 挂载做热更新；生产镜像另建（多阶段、非 root、正式 WSGI 服务器），**不复用 dev Dockerfile**；
- 依赖清单先单独 `COPY` 再 `pip install`，让依赖层吃缓存。

## 4. 四道检查

| 检查 | 命令 | 作用 |
|---|---|---|
| 框架自检 | `python manage.py check` | 配置 / 路由 / 模型一致性 |
| lint | `ruff check .`（一个工具替代 flake8+isort+black） | 风格与常见错误 |
| 类型检查 | `mypy .` | 见下方说明 |
| 测试 | `pytest`（+ `pytest-django`） | `DJANGO_SETTINGS_MODULE` 写进 `pyproject.toml` |

> **mypy 起步姿势**：Django 官方不提供类型存根，未引入 `django-stubs` 时 `strict` 会把每个视图都判成 untyped。
> 先配"基础模式"（`ignore_missing_imports = true` + `check_untyped_defs = true`），
> 把「是否引入 django-stubs」记为一个**待评估项**（它要占依赖预算），而不是假装 strict 已开。

## 5. 健康检查的正确姿势

```python
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """只回答"进程活着吗"——不查数据库。"""
    return JsonResponse({"status": "ok", "service": "<项目名>"})
```

**为什么不查 DB**：进程崩溃与数据库故障是两类故障。健康检查若依赖 DB，
DB 一挂负载均衡会把整个服务判死；而 DB 故障本应由单独的探针回答。

## 6. 踩坑记录

| # | 坑 | 处理 |
|---|---|---|
| 1 | **Windows 控制台 GBK 编码**：脚本输出含 `✅` `↔` 这类字符会抛 `UnicodeEncodeError` | 工具脚本输出只用 GBK 兼容字符（`[OK]` / `[!]` / `vs`）；中文本身没问题 |
| 2 | `import` 与 `from __future__ import annotations` 之类顺序被 lint 挑 | 用 `ruff --fix` 统一处理，别手改 |
| 3 | 依赖元数据里 `License` 字段是**自由文本**（不是标准 SPDX） | 见同目录《许可登记与署名闸》——不为元数据背书，人工核实许可正文 |
| 4 | 本机无 `psql` 客户端也能开发 | PG 走 Docker；`.env` 里端口可用 `POSTGRES_PORT` 避开本机占用 |
