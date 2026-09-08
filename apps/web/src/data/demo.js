// 演示数据：近 7 日开标样例。
// 说明：M0/M1 过渡期用于展示"开标提醒 + 状态登记"交互；M1 接入真实招标主表后本文件退役。
// 日期相对"今天"动态生成，保证任何时候打开都能看到"明日开标"示例。

const pad = (n) => String(n).padStart(2, '0')

export function buildDemoOpenings() {
  const day = (offset) => {
    const d = new Date()
    d.setDate(d.getDate() + offset)
    return d
  }
  const iso = (offset, hm) => {
    const d = day(offset)
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`
  }

  return [
    {
      id: 'd1',
      name: '宁夏宁东 200MW 光伏基地项目 EPC 总承包',
      date: iso(1, '09:30'),
      keywords: ['EPC', '光伏'],
    },
    {
      id: 'd2',
      name: '山西朔州 100MW 风电项目 PC 总承包',
      date: iso(1, '14:00'),
      keywords: ['PC', '风电'],
    },
    {
      id: 'd3',
      name: '河北沧州 220kV 变电站扩建施工项目',
      date: iso(3, '09:00'),
      keywords: ['施工'],
    },
    {
      id: 'd4',
      name: '内蒙古鄂尔多斯 2×660MW 煤电灵活性改造 EPC',
      date: iso(5, '10:00'),
      keywords: ['EPC', '煤电'],
    },
    {
      id: 'd5',
      name: '山东青岛 海底电缆集中采购项目',
      date: iso(6, '09:00'),
      keywords: ['电缆'],
    },
  ]
}

// 相对今天的称呼：今日 / 明日 / 后天 / N 天后
export function relLabel(dateStr) {
  const d = new Date(dateStr.replace(' ', 'T'))
  const now = new Date()
  const a = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const b = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((b - a) / 86400000)
  if (diff <= 0) return '今日'
  if (diff === 1) return '明日'
  if (diff === 2) return '后天'
  return `${diff} 天后`
}
