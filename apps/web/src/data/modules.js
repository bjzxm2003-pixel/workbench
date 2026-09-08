// 业务域与助手模块的单一描述源（后续接入真实数据/后端时在此演进 schema）
export const domains = [
  {
    id: 'bid',
    label: '投标业务',
    en: 'BIDDING OPS',
    icon: 'bolt',
    accent: 'cyan',
    desc: '从计划筛选到开标提醒的招标全流程助手',
    assistants: [
      {
        id: 'monthly',
        name: '月招标计划筛选助手',
        en: 'MONTHLY PLAN FILTER',
        schedule: '手动 · 上传文件',
        trigger: 'manual',
        desc: '上传月招标计划文件，按关键词（EPC / PC / 施工 / 风电 / 煤电 / 光伏 / 电缆）筛查去重，生成招标主表并推送个人微信。',
        progress: 'M1 · 待开发',
      },
      {
        id: 'daily',
        name: '日招标项目筛选助手',
        en: 'DAILY BIDDING CRAWL',
        schedule: '每日 18:00',
        trigger: 'auto',
        desc: '抓取国能e招当日招标公告，关键词筛查后合并更新主表并推送新表；投标单位与状态按你的文字登记自动更新。',
        progress: 'M2 · 待开发',
      },
      {
        id: 'remind',
        name: '招标项目提醒助手',
        en: 'OPENING REMINDER',
        schedule: '每日 09:00',
        trigger: 'auto',
        desc: '筛查主表中“明日开标”的项目，把项目与投标单位信息整理成文字，推送到个人微信提醒。',
        progress: 'M3 · 待开发',
      },
    ],
  },
  {
    id: 'silver',
    label: '银发康养',
    en: 'SILVER CARE MEDIA',
    icon: 'heart',
    accent: 'violet',
    desc: '银发经济自媒体 · 爆款分析与改写',
    assistants: [
      {
        id: 'silver_media',
        name: '银发康养自媒体助手',
        en: 'VIRAL ANALYZER · TOUTIAO',
        schedule: '每日 17:00',
        trigger: 'auto',
        desc: '搜今日头条/小红书“银发经济·康养·养老产业”爆款，取点赞最高 3 篇做四步拆解（标题/核心/框架/改写角度），并改写 1 篇今日头条文案。',
        progress: 'M4 · 待开发',
      },
    ],
  },
  {
    id: 'guoxue',
    label: '国学自媒体',
    en: 'GUOXUE SHORT-VIDEO',
    icon: 'book',
    accent: 'amber',
    desc: '国学 × 个人成长 / 商业智慧 短视频',
    assistants: [
      {
        id: 'guoxue_media',
        name: '国学经典自媒体助手',
        en: 'VIRAL ANALYZER · DOUYIN',
        schedule: '每日 16:00',
        trigger: 'auto',
        desc: '搜抖音/快手等“国学·易经·道德经·黄帝内经·论语·人生智慧”爆款短视频，取 3 条拆解（前3秒/脚本/成功要素），产出 1 分钟改编脚本。',
        progress: 'M5 · 待开发',
      },
    ],
  },
]

// 关键词配置（占位初值，M1 起在界面中可编辑并持久化）
export const keywordPresets = {
  bid: ['EPC', 'PC', '施工', '风电', '煤电', '光伏', '电缆'],
  silver: ['银发经济', '康养', '养老产业'],
  guoxue: ['国学', '易经', '道德经', '黄帝内经', '论语', '人生智慧'],
}
