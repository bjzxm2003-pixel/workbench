# 个人工作台 · Workbench

> 暗黑科技风 · 左侧四大入口：◎ 今日总览 ｜ ⚡ 投标业务 ｜ 🧓 银发康养 ｜ 📜 国学自媒体

个人自动化工作台：聚合 5 个助手（月招标计划筛选、日招标项目筛选、开标提醒、银发康养爆款分析改写、国学短视频分析改编脚本）。
定时任务依托 GitHub Actions，结果经 Server酱 推送个人微信，AI 创作调用 DeepSeek API。

## 整体框架
见 [`docs/整体框架.md`](docs/整体框架.md)（随里程碑持续更新，为“活文档”）。

## 目录结构
```
apps/web     工作台前端（Vue3 + Vite，暗黑科技主题）  ← M0 外壳就绪
server/      FastAPI 后端（上传/预检/主表/状态登记/导出/推送） ← M1 已接入
jobs/        定时执行脚本（GitHub Actions 调用）          ← M2 起落地
data/        主表 master_bids.json / 导出物 / 样例（导出物与样例不入库）
docs/        文档
```

## 本地运行（M1：月招标计划筛选助手已可用）

```bash
# 1) 后端 FastAPI（端口 8000）
cd /Users/zhangxinming/Desktop/harness
server/.venv/bin/python -m venv server/.venv              # 仅首次
server/.venv/bin/pip install -r server/requirements.txt   # 仅首次
server/.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000

# 2) 前端 Vite（端口 5173）
cd apps/web
npm install      # 仅首次
npm run dev      # 打开 http://127.0.0.1:5173
```

- 后端密钥：`server/.env`（或项目根 `.env`）填 `SCKEY=…` 即可推送个人微信，不填则自动跳过推送并在界面提示。
- 月计划文件支持 xlsx / csv / 文本型 PDF；表头自动识别（项目名称 / 预计发布公告时间 等别名）。
- 产物：主表 `data/bidding/master_bids.json`；导出 xlsx/csv 在 `data/bidding/exports/`（不入库，可在工作台下载）。

## 实施路线图
- [x] M0 框架脚手架 + 今日总览 + 投标业务提醒模块（状态登记入口）
- [x] M1 ①月招标计划筛选助手（上传→筛查去重→主表→xlsx/csv→可选推送微信）
- [x] M2 ②日招标项目筛选助手（18:00 抓国能e招→合并主表→推送，本地可手动触发）
- [x] M3 ③招标项目提醒助手（09:00 明日开标提醒，本地可手动推送测试）
- [x] M4 ④银发康养自媒体助手（17:00 · 头条热榜+AI 模拟 → 四步拆解 → 头条改写文案）
- [ ] M5 ⑤国学自媒体助手（16:00）
- [ ] M6 打磨：稳定性 / 运行历史 / 文档

## 密钥（绝不入库）
本地 `.env`（gitignore）+ GitHub Secrets：`SCKEY`（Server酱）、`DEEPSEEK_API_KEY`。
