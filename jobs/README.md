# jobs/ — 定时任务执行脚本（M1 起逐步落地）

5 个助手脚本，由 GitHub Actions cron 或工作台手动触发运行，产出写入 `../data/` 并推送 Server酱。

| 助手 | 脚本（规划） | 触发（北京） |
|---|---|---|
| ① 月招标计划筛选 | `monthly_plan.py` | 手动（上传文件） |
| ② 日招标项目筛选 | `daily_bidding.py` | 18:00 |
| ③ 招标项目提醒 | `open_reminder.py` | 09:00 |
| ④ 银发康养自媒体 | `silver_media.py` | 17:00 |
| ⑤ 国学自媒体 | `guoxue_media.py` | 16:00 |
