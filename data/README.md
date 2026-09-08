# data/ — 运行数据（主表/历史/报告产物）

- `bidding/master_bids.json` 招标主表（唯一数据源），每次运行导出 `.xlsx` 存档
- `bidding/history.json` 抓取历史（去重）
- `media/reports/` ④⑤ 的分析报告与改写产物

随 GitHub Actions 运行提交更新。
