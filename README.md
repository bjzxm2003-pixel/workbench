# 个人工作台 · Workbench

> 暗黑科技风 · 左侧三大业务域：⚡ 投标业务 ｜ 🧓 银发康养 ｜ 📜 国学自媒体

个人自动化工作台：聚合 5 个助手（月招标计划筛选、日招标项目筛选、开标提醒、银发康养爆款分析改写、国学短视频分析改编脚本）。
定时任务依托 GitHub Actions，结果经 Server酱 推送个人微信，AI 创作调用 DeepSeek API。

## 整体框架
见 [`docs/整体框架.md`](docs/整体框架.md)（随里程碑持续更新，为“活文档”）。

## 目录结构
```
apps/web     工作台前端（Vue3 + Vite，暗黑科技主题）  ← M0 已就绪
server/      FastAPI 后端（上传/手动触发/状态登记/产物下载） ← M1 起落地
jobs/        5 个助手的定时执行脚本（GitHub Actions 调用）   ← M1 起落地
data/        主表/历史/报告产物（随运行 commit）
docs/        文档
```

## 本地运行（当前阶段：M0 界面外壳）
```bash
cd apps/web
npm install
npm run dev        # 打开 http://127.0.0.1:5173
npm run build      # 产物在 apps/web/dist
```

## 实施路线图
- [x] M0 框架脚手架：项目结构 + 暗黑科技风工作台外壳（左侧三导航 + 占位页）
- [ ] M1 ①月招标计划筛选助手
- [ ] M2 ②日招标项目筛选助手
- [ ] M3 ③招标项目提醒助手
- [ ] M4 ④银发康养自媒体助手
- [ ] M5 ⑤国学自媒体助手
- [ ] M6 打磨：仪表盘/运行历史/稳定性/文档

## 密钥（绝不入库）
本地 `.env`（gitignore）+ GitHub Secrets：`SCKEY`（Server酱）、`DEEPSEEK_API_KEY`。
