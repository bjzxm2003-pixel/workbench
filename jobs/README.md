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
- 设置环境变量 `TOUTIAO_SEARCH_API`（SearchApi / Tavily 风格，返回 `organic_results[].link`）
- 或在 `data/media/toutiao_candidates.txt` 每行写一个头条文章链接，任务会逐个核实标题与发布时间

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

