# Serenity 项目自审报告

更新时间：2026-06-11

## 1. 审查结论

Serenity 已具备前后端分离的基本工程形态：`backend/` 负责 FastAPI、数据库模型、Celery worker 和外部服务边界；`frontend/` 负责 Vue 运维看板；`docs/database-design.md` 已覆盖数据库结构、索引、状态机和自检。

本轮自审后的结论：

- 可以作为“运维看板 + 同步链路骨架”的开发基线。
- 数据库设计文档和现有 SQLAlchemy 模型方向一致。
- 后端测试可运行，前端可构建。
- 上线前必须补齐真实 `.env`、DNS、Caddy 站点块和外部服务烟测。
- 当前 DeepSeek、飞书、COS 属于配置驱动和边界类能力，不能在生产手册里宣称已经完成真实闭环验收。
- 第二轮复查发现并修复了生产默认密钥可误启动、Celery Beat 不处理同步 run、后端容器 root 运行、前端缺少直接访问安全头等问题。

## 2. 已完成的必要修复

### 2.1 仓库卫生

- 已清理 `frontend/node_modules`、`frontend/dist`、Python `__pycache__`、`backend/.pytest_cache`。
- 已新增 `.dockerignore`，避免 `.env`、缓存、数据库文件、构建产物进入 Docker build context。
- `.gitignore` 已覆盖 `.env`、`node_modules`、`dist`、`.pytest_cache`、`__pycache__`、数据库文件。

### 2.2 前端生产镜像

原问题：`frontend/Dockerfile` 使用 `npm run dev` 启动 Vite dev server，不适合正式域名上线。

已修复：

- 使用 `node:22-alpine` 构建前端静态文件。
- 使用 `nginx:1.27-alpine` 提供生产静态服务。
- `frontend/nginx.conf` 支持 Vue history 路由回退。
- 本地直接访问前端容器时，`/api/*` 可反代到 `serenity-backend:8000`。

### 2.3 Compose 网关适配

已调整：

- backend 容器名固定为 `serenity-backend`。
- frontend 容器名固定为 `serenity-frontend`。
- backend 和 frontend 加入外部 Docker 网络 `shared_gateway`。
- PostgreSQL 和 Redis 保留在项目默认网络，避免暴露给网关。
- 本机预览端口只绑定 `127.0.0.1`。

### 2.4 环境变量模板

已调整 `.env.example`：

- 增加 `APP_ENV=production`，生产模式会拒绝默认管理员密码、默认 JWT secret 和默认数据库密码。
- 增加 `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`。
- 增加 `SERENITY_BACKEND_PORT`、`SERENITY_FRONTEND_PORT`、`SHARED_CADDY_NETWORK`。
- `CORS_ORIGINS` 默认包含 `https://serenity.zenithy.art` 和本地预览地址。
- DeepSeek 默认模型保留 `deepseek-v4-pro`。

### 2.5 第二轮安全与运维修复

- `create_app`、`init-db`、Celery worker/beat 启动时都会执行生产安全校验。
- Compose 默认把后端、init、worker、beat 置为 `APP_ENV=production`，即使服务器忘记 `.env` 也不会带弱默认值启动。
- `poll_accounts` 创建同步轮次后会把每个 run 入队给 `process_sync_run`。
- 后端 Docker 镜像改为非 root 用户运行，并保留 `/app` 写权限以支持 Celery Beat。
- Compose 为长期服务增加 `restart: unless-stopped`，backend 增加 `/api/health` 容器健康检查。
- 前端 nginx 增加 CSP、Permissions-Policy、Referrer-Policy、X-Content-Type-Options、X-Frame-Options。

### 2.6 第三轮可重复门禁

- 新增 `scripts/verify-local.ps1`，一键执行后端测试、Python 编译、前端类型检查、前端构建、Compose config、敏感信息扫描，并自动清理生成物。
- `scripts/verify-local.ps1` 会显式检查 Python、npm、Docker 等原生命令退出码，避免命令失败但脚本仍显示成功。
- 新增 `scripts/smoke-compose.ps1`，用临时项目名、临时端口和临时卷启动整套 Compose，并检查后端健康接口和前端首页。
- 新增 `.github/workflows/ci.yml`，GitHub 上传后自动执行同等源码级质量门禁。
- Dockerfile 支持可切换基础镜像、APT 镜像、PyPI 镜像和 npm registry。
- 去掉 Dockerfile `# syntax=docker/dockerfile:1.7`，避免国内服务器先去 Docker Hub 拉 `docker/dockerfile` 导致构建失败。
- 已用 `docker.m.daocloud.io`、清华 APT/PyPI、npmmirror 实测完成 backend/frontend 镜像构建。
- `ADMIN_PASSWORD`、`JWT_SECRET`、`POSTGRES_PASSWORD` 改为 Compose 级必填，避免没有 `.env` 时服务带弱默认密钥启动，或 PostgreSQL 先用弱默认密码创建数据卷。

## 3. 仍需注意的风险

### Blocker

- 生产前必须配置真实 `ADMIN_PASSWORD`、`JWT_SECRET`、`POSTGRES_PASSWORD`，不能使用 `.env.example` 的占位值。
- 生产前必须确认 `serenity.zenithy.art` DNS 已指向 Caddy 网关服务器。
- 生产前必须确认服务器存在 Docker 网络 `shared_gateway`。
- Caddy 网关配置需要人工复制站点块并执行 `caddy fmt`、`caddy validate`、`caddy reload`。

### Suggestion

- 真实 X、DeepSeek、Feishu、COS 全链路建议补集成测试后再宣称生产可用。
- COS 客户端当前只定义边界和公开 URL 生成，后续应接入 S3 兼容 SDK 并补上传失败重试测试。
- 飞书 webhook 如启用签名校验，应在客户端中补时间戳和 HMAC 签名逻辑。
- `translation_jobs`、`push_logs` 和 `task_attempts` 已建模，后续应把 Celery 媒体、翻译、推送任务真正串联起来。

### Nit

- README 只保留快速入口，详细步骤放到 `docs/傻瓜式部署手册.md`。
- 文档中的仓库名、服务器路径、域名统一通过 `docs/上线变量卡.md` 管理，避免多处散落。

## 4. 已验证项

本轮要求验证：

- 后端：`cd D:\apps\serenity\backend && python -m pytest -q`
- 前端：`cd D:\apps\serenity\frontend && npm run build`
- Compose：`cd D:\apps\serenity && docker compose config`

本次验证结果：

- 后端测试：通过，`9 passed in 3.74s`。
- Python 语法编译：通过，`python -m compileall -q app`。
- 前端类型检查：通过，`npm run typecheck`。
- 前端构建：通过，Vite 生产构建成功。
- Compose 配置：通过，`docker compose config` 可正常展开；backend/frontend 已加入 `shared_gateway`。
- 敏感信息扫描：通过，未发现常见 API key、Bearer token、AWS/GCP/飞书类密钥形态。
- Docker 镜像构建：官方 Docker Hub 访问超时；切换 `docker.m.daocloud.io` 基础镜像、清华 APT/PyPI、npmmirror 后，`docker compose build backend frontend` 通过。
- 本地一键预检：`powershell -ExecutionPolicy Bypass -File .\scripts\verify-local.ps1 -DockerBuild` 通过。
- Compose 运行时烟测：`powershell -ExecutionPolicy Bypass -File .\scripts\smoke-compose.ps1` 通过，backend、frontend、worker、beat、postgres、redis 均能启动；`/api/health` 和前端首页可访问；临时容器和临时卷已清理。

工具风险：

- Qartez 索引当前仍指向旧 `serenity_sync` 结构，和当前 `backend/frontend/docs` 结构不一致；本轮复查以文件系统当前状态、测试和构建输出作为权威证据。

如果后续修改代码，需要重新执行以上三项检查后再 Git 上传。

## 5. 外部服务安全要求

参考 `helper-paper` 的 DeepSeek 使用规则，本项目执行以下要求：

- 默认模型使用 `deepseek-v4-pro`。
- 只有在速度或成本优先时才考虑切换轻量模型。
- 不把 DeepSeek、X、Feishu、COS、OpenAI 或其他 API key 写入 GitHub、README、部署手册、日志或截图。
- 外部翻译能力上线前必须先做 key 烟测，再做应用链路烟测。
- 任何失败日志只记录状态码、错误类型和 request id，不记录密钥原文。

## 6. 后续优化清单

按优先级排序：

1. 补齐 COS S3 兼容上传实现和失败重试。
2. 补齐 DeepSeek 翻译任务入库、token 统计、超时重试。
3. 补齐飞书 webhook 签名、payload 结构测试和失败退避。
4. 增加端到端 mock 集成测试：X 新帖 -> 入库 -> 翻译 -> 媒体归档 -> 飞书推送日志。
5. 增加 GitHub Actions：后端测试、前端构建、Docker Compose config 检查。
6. 给 `/api/health` 增加数据库和 Redis 深度检查。
