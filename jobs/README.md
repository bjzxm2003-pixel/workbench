# jobs/ — 定时任务执行脚本

| 助手 | 脚本 | 触发（北京） | 状态 |
|---|---|---|---|
| ② 日招标项目筛选 | `daily_bidding.py`（爬虫 `crawl_bidding.py`） | 每日 18:00 · GH Actions / 手动 | ✅ M2 已接入 |
| ③ 招标项目提醒 | `open_reminder.py`（规划） | 每日 09:00 | M3 |
| ④ 银发康养自媒体 | `silver_media.py`（规划） | 每日 17:00 | M4 |
| ⑤ 国学自媒体 | `guoxue_media.py`（规划） | 每日 16:00 | M5 |

本机运行：`python jobs/daily_bidding.py [--date YYYY-MM-DD] [--no-push|--push]`
轻量依赖：`requirements-jobs.txt`（GH Actions 使用）
