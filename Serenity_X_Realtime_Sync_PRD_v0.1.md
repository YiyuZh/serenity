# Serenity X 官方 API 实时同步飞书服务 PRD v0.1

**Status**: Approved for Implementation  
**Last Updated**: 2026-06-11  
**Version**: 0.1  
**Primary Account**: `@aleabitoreddit`

---

## 1. Problem Statement

Serenity 需要一个 7x24 小时运行的内容同步服务，用官方 X API 监听指定公开账号的新 Posts，将正文和图片结构化保存，并把“原文 + 忠实专业中文翻译 + 原帖链接 + 图片链接”推送到飞书群，减少人工巡检、复制、翻译和转发成本。

当前 v1 不做网页爬虫，不模拟浏览器，不登录 X 账号，不抓取 profile 信息，不进行点赞、评论、转发等互动行为。

## 2. Goals & Success Metrics

| Goal | Metric | Target |
|------|--------|--------|
| 及时同步 | 新帖发布到飞书推送完成的延迟 | 95% 在 5 分钟内完成 |
| 准确去重 | 同一 `post_id` 重复推送次数 | 0 |
| 翻译可用 | 译文保留原文事实、数字、时间、代码、链接和专业术语 | 人工抽检通过 |
| 稳定运行 | 服务连续运行 | 24 小时无未处理异常 |
| 可追踪 | 每条 post 生命周期日志 | 抓取、媒体、翻译、推送均可查询 |

## 3. Non-Goals

- 不抓取主页签名 bio、头像、背景图、粉丝数等 profile 信息。
- 不使用 cookie，不模拟浏览器，不绕过 X 风控。
- 不做点赞、评论、转发、私信或自动登录。
- 不做图片 OCR 翻译。
- 不做飞书内指令、用户订阅、私聊或交互式回调。
- 不实现订单、支付、库存、数字商品发货或售卖结算。
- 不递归展开整条线程；引用、回复、转帖只保存关系和链接。

## 4. User Stories & Acceptance Criteria

### Story 1: 新帖同步

作为运营人员，我希望指定账号发布新帖后自动进入飞书群，这样我不需要手动巡检。

**Acceptance Criteria**
- Given `@aleabitoreddit` 发布公开新帖，when 下一轮同步执行，then 系统通过 X 官方 API 获取新帖。
- Given 新帖已保存过，when 下一轮同步再次看到同一 `post_id`，then 不重复翻译和推送。
- Given X API 返回 rate limit，when 同步任务执行，then 系统进入退避冷却并记录 reset 时间。

### Story 2: 原文和译文推送

作为飞书群成员，我希望先看到原文，再看到忠实专业中文翻译，这样能保留上下文同时快速理解内容。

**Acceptance Criteria**
- Given post 有正文，when 翻译成功，then 飞书消息按“原文 -> 中文翻译 -> 原帖链接 -> 图片链接”顺序展示。
- Given post 中包含数字、百分比、时间、代码、股票代码、专有名词，when 翻译，then 这些事实不得被改写或新增。
- Given post 没有正文但有媒体，when 推送，then 保留原帖链接和媒体链接，并标记无正文可翻译。

### Story 3: 图片保存

作为维护人员，我希望图片被保存到腾讯云 COS，这样即使原图链接变化，也能保留可访问副本。

**Acceptance Criteria**
- Given X API 返回图片媒体，when 媒体 worker 运行，then 图片下载并上传到腾讯云 COS。
- Given 图片上传失败，when 重试次数未耗尽，then 系统按退避策略重试并记录错误。
- Given 飞书推送消息生成，when 图片已上传，then 消息包含 COS 可访问链接。

## 5. Solution Overview

v1 使用轮询方案而非 Filtered Stream。服务通过 X API v2 解析 `@aleabitoreddit` 的 user id，并使用 `GET /2/users/{id}/tweets` 轮询最新 Posts。每轮同步使用 `since_id` 避免重复扫描，数据库以 `post_id` 做唯一约束保证幂等。

系统采用 Python 服务、Docker Compose、PostgreSQL、Redis、Celery Beat + Celery Worker。图片保存到腾讯云 COS；飞书只使用自定义群机器人 webhook 单向推送。配置和运维通过 `.env`、YAML/环境变量与 CLI 完成，不建设 Web 管理后台。

## 6. Functional Scope

### Phase 1: Core Sync

- 账号解析：将 `@aleabitoreddit` 解析为 X user id。
- 官方 API 轮询：每 180 秒轮询一次，验收 SLA 为 5 分钟内推送。
- 去重：使用 `post_id` 唯一索引。
- 正文提取：保存正文、语言、发布时间、原帖链接、引用/回复/转帖关系。
- 主帖策略：只翻译主帖正文；引用、回复、转帖保存关系，不递归展开。
- 图片保存：下载图片并上传腾讯云 COS，保存 `storage_url`。
- 翻译：调用 DeepSeek `deepseek-v4-pro`，输出忠实专业简体中文译文。
- 飞书推送：通过群机器人 webhook 推送原文、译文、原帖链接和图片链接。
- 重试：媒体、翻译、推送失败后自动重试。
- 日志：记录同步轮次、API 状态、错误原因和每条 post 生命周期。

### Phase 2: Operational Hardening

- CLI：`resolve-user`、`sync-once`、`retry-failed`、`healthcheck`。
- 健康检查：数据库、Redis、关键配置项检查。
- 监控字段：token 使用量、任务耗时、重试次数、最后成功同步时间。
- 删除/下架能力：支持将已保存 post 标记为 `skipped` 或停止后续推送。

### Phase 3: Reserved Extension Points

- `PostReadyEvent`：当帖子完成媒体保存和翻译后发出内部事件，供未来发货、渠道分发或其他消费系统接入。
- 关键词高亮、翻译质量复查、字段检查、视频链接保存、Filtered Stream 近实时监听仅保留接口，不进入 v1 验收。
- 自动发货系统仅保留扩展接口；本轮不实现订单、支付、库存或数字商品发送。
- 删除用户订阅系统，不再作为本项目功能。

## 7. API & Integration Requirements

### X API

- Base URL 默认 `https://api.x.com/2`，可通过 `X_API_BASE_URL` 覆盖。
- 用户解析：`GET /2/users/by/username/{username}`。
- 帖子轮询：`GET /2/users/{id}/tweets`。
- 参数：
  - `max_results=10`
  - `since_id=<last_seen_post_id>`
  - `tweet.fields=id,text,created_at,lang,conversation_id,referenced_tweets,attachments,author_id,entities,public_metrics`
  - `expansions=attachments.media_keys,referenced_tweets.id`
  - `media.fields=media_key,type,url,preview_image_url,width,height,alt_text`

### DeepSeek

- Base URL 默认 `https://api.deepseek.com`。
- Endpoint：OpenAI-compatible `POST /chat/completions`。
- Model：默认 `deepseek-v4-pro`，允许通过 `DEEPSEEK_MODEL` 覆盖。
- Temperature：`0.2`。
- Prompt 要求：忠实翻译为简体中文；专业名词需理解后翻译；保留数字、时间、百分比、代码、链接、股票代码和专有名词；禁止添加原文没有的信息。

### Feishu

- 只支持自定义群机器人 webhook。
- 支持 webhook secret 签名。
- 消息格式优先使用 rich post；无法直接上传图片时，使用 COS 链接展示图片。
- 不实现飞书开放平台应用机器人、用户私聊、群指令或回调。

### Tencent Cloud COS

- 使用 S3-compatible 客户端。
- 通过 `COS_ENDPOINT`、`COS_BUCKET`、`COS_REGION`、`COS_SECRET_ID`、`COS_SECRET_KEY` 配置。
- 可选 `COS_PUBLIC_BASE_URL` 用于生成公开访问链接。

## 8. Configuration

Required:

- `X_BEARER_TOKEN`
- `DEEPSEEK_API_KEY`
- `FEISHU_WEBHOOK_URL`
- `COS_ENDPOINT`
- `COS_BUCKET`
- `COS_REGION`
- `COS_SECRET_ID`
- `COS_SECRET_KEY`

Optional:

- `X_ACCOUNT_HANDLE=aleabitoreddit`
- `X_API_BASE_URL=https://api.x.com/2`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-pro`
- `FEISHU_WEBHOOK_SECRET`
- `COS_PUBLIC_BASE_URL`
- `POLL_INTERVAL_SECONDS=180`
- `X_MAX_RESULTS=10`
- `RETRY_MAX_ATTEMPTS=3`

## 9. Data Model

状态枚举统一为：

`pending`、`running`、`succeeded`、`failed`、`retrying`、`skipped`

Core tables:

- `source_accounts`: 保存账号 handle、user id、`since_id`、是否启用、最后同步时间。
- `posts`: 保存原文、译文、X 元数据、生命周期状态、错误信息、原始 JSON。
- `media_assets`: 保存图片原始链接、COS 路径、COS URL、媒体状态、重试信息。
- `translation_jobs`: 保存翻译输入、输出、模型、token 使用量、状态和错误。
- `push_logs`: 保存飞书 payload、目标、状态、重试信息和推送时间。
- `sync_runs`: 保存每轮同步的开始/结束时间、抓取数量、新增数量和错误。

## 10. System Architecture

```text
Celery Beat / CLI
      |
      v
Sync Service
      |
      v
X API Client -> Post Normalizer -> Deduplication -> PostgreSQL
                                                |
                                                v
Media Worker -> Tencent COS
                                                |
                                                v
Translation Worker -> DeepSeek
                                                |
                                                v
PostReadyEvent -> Feishu Push Worker -> Feishu Group
```

## 11. Retry & Failure Handling

- X rate limit：读取 reset header，冷却到 reset 时间；无法读取时退避 5 分钟。
- 网络错误：指数退避，最大 `RETRY_MAX_ATTEMPTS`。
- 媒体上传失败：保留原始 URL，标记媒体失败，不阻塞正文翻译；推送时附原始链接并标记媒体未归档。
- 翻译失败：不推送译文，进入重试；超过重试次数后标记 `failed`。
- 飞书推送失败：保留 payload 和错误，进入重试；不重复生成翻译。

## 12. Deployment

- Target：腾讯云 Linux CVM。
- Runtime：Docker Compose。
- Services：`app`、`worker`、`beat`、`postgres`、`redis`。
- Init：`python -m serenity_sync.cli init-db`。
- Manual sync：`python -m serenity_sync.cli sync-once --inline`。
- Worker：`celery -A serenity_sync.celery_app worker --loglevel=INFO`。
- Beat：`celery -A serenity_sync.celery_app beat --loglevel=INFO`。

## 13. Test Plan

- Unit tests:
  - X API response normalization.
  - `post_id` dedup behavior.
  - 主帖、引用、回复、转帖识别。
  - DeepSeek prompt 和译文提取。
  - 飞书 rich post payload 和 webhook 签名。
  - COS object key 生成。
  - 状态流转。
- Integration tests:
  - Mock X、DeepSeek、Feishu、COS，验证新帖到推送日志完整链路。
  - 验证重复 post 不重复推送。
  - 验证无图、多图、空正文、API 失败、翻译失败、飞书失败。
- Deployment acceptance:
  - Docker Compose 启动成功。
  - `init-db` 成功建表。
  - `sync-once --inline` 能完成一次同步。
  - 服务连续运行 24 小时无未处理异常。

## 14. Launch Checklist

- [ ] 已配置 X API Bearer Token。
- [ ] 已配置 DeepSeek API Key 和模型名。
- [ ] 已创建飞书群机器人 webhook，并按需配置 secret。
- [ ] 已创建腾讯云 COS bucket、访问密钥和公开访问策略。
- [ ] 已在腾讯云 CVM 安装 Docker 和 Docker Compose。
- [ ] 已执行 `init-db`。
- [ ] 已完成一次 `sync-once --inline` 验证。
- [ ] 已启动 worker 和 beat。
- [ ] 已确认日志能追踪抓取、媒体、翻译、推送状态。

## 15. References

- X API: https://docs.x.com/x-api/users/get-posts
- DeepSeek API: https://api-docs.deepseek.com/
- Feishu Custom Bot: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
- Tencent Cloud COS S3 Compatibility: https://www.tencentcloud.com/document/product/436/32537
