# jobs/ — 定时任务执行脚本

| 助手 | 脚本 | 触发（北京） | 状态 |
|---|---|---|---|
| ② 日招标项目筛选 | `daily_bidding.py`（爬虫 `crawl_bidding.py`） | 每日 18:00 | ✅ M2 |
| ③ 招标项目提醒 | `open_reminder.py` | 每日 09:00 | ✅ M3 |
| ④ 银发康养自媒体 | `silver_media.py` | 每日 17:00 | ✅ M4 |
| ⑤ 国学经典自媒体 | `guoxue_media.py` | 每日 16:00 | ✅ M5 |
| ⑥ 今日头条文案包（国学×康养） | `toutiao_copy.py` | 每日 23:00 | ✅ M6 |

本机运行示例：
```
python -m jobs.daily_bidding  [--date YYYY-MM-DD] [--no-push|--push]
python -m jobs.open_reminder  [--as-of YYYY-MM-DD] [--no-push|--push]
python -m jobs.silver_media   [--date YYYY-MM-DD] [--no-push|--push]
python -m jobs.guoxue_media   [--date YYYY-MM-DD] [--no-push|--push]
python -m jobs.toutiao_copy   [--date YYYY-MM-DD] [--no-push|--push]
```
密钥：`SCKEY`（推送）、`DEEPSEEK_API_KEY`（M4/M5/M6 创作），取 server/.env / 项目根 .env / GitHub Secrets。
轻量依赖：`requirements-jobs.txt`。

---

## M6 今日头条文案助手（`toutiao_copy.py`）

每日 23:00 产出：**国学 3 条 + 康养 3 条爆款主题**，以及**国学 3 篇 + 康养 3 篇今日头条纯文字文案**。

产出文件：
- `data/media/reports/toutiao_copy_<date>.md` — 报告（数据核实 + 主题 + 正文）
- `data/media/reports/toutiao_data_<date>.csv` — 数据底表
- `data/media/toutiao_last_run.json` — 运行记录

**与 M4/M5 的关键差别**：M4/M5 数据不足时用「AI 趋势模拟 + 模拟点赞」补齐；**M6 一律不输出任何互动量数字**
（平台不公开阅读/点赞/评论/收藏/转发），只用两类硬证据：① 热榜真实 `热度值`；② 文章页核实的真实标题与发布时间。

**可选增强**（不配置也能跑）：
- 或在 `data/media/toutiao_candidates.txt` 每行写一个头条文章链接，任务会逐个核实标题与发布时间
- 或配置搜索 API 自动发现新链接（`TOUTIAO_SEARCH_API`），见下

**`TOUTIAO_SEARCH_API` 怎么填**（配到 GitHub Secrets 后无需再手工维护链接清单）：

| 写法 | 填入内容 | 请求方式 |
|---|---|---|
| **裸 key（推荐，最省事）** | `tvly-xxxxxxxx` | 自动走 `POST https://api.tavily.com/search` |
| 带 key 的 URL | `https://api.tavily.com/search?api_key=tvly-xxxxxxxx` | 同上（自动去掉 query 里的 key，改用 Bearer + body） |
| 普通 endpoint（Serper 等） | `https://serpapi.com/search?engine=google` | GET `?q=<查询词>` |

- 判定规则：**先看是不是裸 key**（不含 `/` 与 `?` → 按 Tavily 处理）；否则 **URL 里带 `api_key=` 就走 POST** 分支。与域名无关，中转域名同样适用。
- 响应格式不敏感：递归抽取任意层级里的 `link`/`url`/`href`/`source_url`，只保留 `toutiao.com` 域。
- 每次运行发 **2 个查询**，结果缓存 6 小时（`data/media/.toutiao_search_cache.json`，不入库）。
- 搜索失败或未返回头条链接**不报错、不影响主流程**，只打印 `[warn]` 并回退到本地清单。

**接 Tavily 的完整步骤**：
1. 注册取 key：<https://app.tavily.com> → API Keys → 复制（形如 `tvly-…`）
2. **先在本地预检**（避免配错 key 白等一次定时任务）：
   ```
   TOUTIAO_SEARCH_API='tvly-你的key' python -m jobs.check_search
   ```
   预检会打印写法识别结果 → 真实调用 2 个查询 → 对抽到的头条链接逐条 `parse_article` 回源核实。
3. 预检通过后在 GitHub 填：仓库 Settings → Secrets and variables → Actions → New repository secret，
   Name 填 `TOUTIAO_SEARCH_API`，Secret 填 **key 本身**（或完整 URL）。
4. 之后每天 23:00 自动发现新链接，`toutiao_candidates.txt` 不用再手工维护。

**标题字数规范（8-20 字，平台口径：CJK/全角按 1、ASCII 按 0.5）**：
`fit_title()` 负责超长标题截断与成稿标题回退；**过短标题不丢弃、不改写**，而是：
- 在主题/文案处内联标注 `⚠️ 待优化`；
- 集中写入报告「待人工优化清单」（类型/赛道/标题原文/实际字数/原因）；
- 计入运行记录 `needs_review` 与 `needs_review_items`。

清单为空时该节自动省略，报告节号会相应顺延（不会出现跳号）。
这样模型偶发产出过短标题时，其余内容照常可用，人工只需按清单改写标题、无需重新生成正文。

**局限**：头条搜索接口 `/api/search/content/` 对无登录请求返回 `count: 0`，故文章级证据需靠上述两种方式补入；
热榜每日只覆盖社会热点，国学/康养并非每日上榜，数据不足时报告会显式给出局限说明。

---

## 内容风控兜底（`server/llm.py`，M4/M5/M6 共用）

DeepSeek 对**整段 messages 入参**做内容安全审核，命中即返回
`400 Content Exists Risk / INVALID_REQUEST`。两类故障及对策：

| 故障类型 | 表现 | 对策（已内置） |
|---|---|---|
| 偶发 / 输出侧 | 同一提示词有时通过、有时被拦 | 原样重试，再用**低温度**（0.3）重发换生成路径 |
| 会话级封禁 | 敏感片段进入上下文后**每次**都 400 | 判定并抛 `LLMBlocked`，请求体落盘取证，作业层跳过该条继续跑 |

每次调用最多尝试 3 次：`original → retry-low-temp → sanitized`（净化会去掉链接/数字/平台名，有损语义，故放在最后）。
同一段文本连续被拦 3 次即判定会话级封禁，不再无意义重试。

被拦请求的完整原文落盘至 `data/media/blocked/blocked_<时间>_<fingerprint>_a<N>.json`，
含 `messages` 原文、`request_id`、`response_head`，可用于在新会话中二分定位触发片段。
`toutiao_copy.py` 还会把被拦条目写进报告并计入运行记录 `blocked` 字段——**绝不让单条文案把整轮 run 变成「处理失败」**。

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_BASE_URL` | 官方接口 | 覆盖接口地址，便于切换供应商兜底 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 覆盖模型名 |
| `DEEPSEEK_MAX_ATTEMPTS` | `3` | 单次调用最大尝试次数（1-5） |
| `DEEPSEEK_BLOCK_DIR` | `data/media/blocked` | 被拦请求取证落盘目录 |

排查工具（见 `jobs/diag_risk*.py`）：
```
python -m jobs.diag_risk --dry-run     # 打印将发送的请求体（不调用 API）
python -m jobs.diag_risk --repro       # 按真实链路抓当天证据后探测
python -m jobs.diag_risk --bisect      # 对证据行二分定位触发片段
python -m jobs.diag_risk_ab            # 提示词 A/B 对照实验
python -m jobs.diag_risk_output        # 验证输出侧偶发拦截
```

