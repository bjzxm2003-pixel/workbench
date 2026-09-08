# jobs/ — 定时任务执行脚本

| 助手 | 脚本 | 触发（北京） | 状态 |
|---|---|---|---|
| ② 日招标项目筛选 | `daily_bidding.py`（爬虫 `crawl_bidding.py`） | 每日 18:00 | ✅ M2 |
| ③ 招标项目提醒 | `open_reminder.py` | 每日 09:00 | ✅ M3 |
| ④ 银发康养自媒体 | `silver_media.py` | 每日 17:00 | ✅ M4 |
| ⑤ 国学经典自媒体 | `guoxue_media.py` | 每日 16:00 | ✅ M5 |

本机运行示例：
```
python -m jobs.daily_bidding  [--date YYYY-MM-DD] [--no-push|--push]
python -m jobs.open_reminder  [--as-of YYYY-MM-DD] [--no-push|--push]
python -m jobs.silver_media   [--date YYYY-MM-DD] [--no-push|--push]
python -m jobs.guoxue_media   [--date YYYY-MM-DD] [--no-push|--push]
```
密钥：`SCKEY`（推送）、`DEEPSEEK_API_KEY`（M4/M5 创作），取 server/.env / 项目根 .env / GitHub Secrets。
轻量依赖：`requirements-jobs.txt`。
