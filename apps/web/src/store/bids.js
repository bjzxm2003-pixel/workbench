// 投标数据仓库：真实主表（后端）优先，离线/空表时降级为本地演示数据。
import { reactive } from 'vue'
import { apiGet, apiPost, apiUpload } from '../api'
import { openingsView, demoState, registerProject, removeRegistration } from './demo'

export const bids = reactive({
  state: 'loading', // loading | master | demo | error
  rows: [], // 主表行（后端 schema）
  updated_at: null,
  error: '',
  keywords: [], // 当前投标关键词（后端配置）
  sc: false, // Server酱 是否已配置
})

export async function loadHealth() {
  try {
    const h = await apiGet('/api/health')
    bids.keywords = h.keywords || []
    bids.sc = !!h.sc_configured
    return h
  } catch {
    return null
  }
}

export async function refreshMaster() {
  bids.state = 'loading'
  try {
    const m = await apiGet('/api/bids/master')
    if (m.rows && m.rows.length) {
      bids.rows = m.rows
      bids.updated_at = m.updated_at
      bids.state = 'master'
    } else {
      bids.rows = []
      bids.updated_at = null
      bids.state = 'demo'
    }
    bids.error = ''
  } catch (e) {
    bids.state = 'error'
    bids.error = String(e.message || e)
  }
  return bids
}

// ---------- 月计划筛选助手 ----------
export const uploadPlan = (file) => apiUpload('/api/bids/master/upload', file)
export const previewSample = () => apiPost('/api/bids/master/preview-sample', {})
export const confirmPlan = async (token, push) => {
  const r = await apiPost('/api/bids/master/confirm', { token, push })
  await refreshMaster()
  return r
}

// ---------- M2：日招标项目筛选助手 ----------
export const dailyStatus = () => apiGet('/api/jobs/daily/status')
export const runDailyJob = async (push) => {
  const r = await apiPost('/api/jobs/daily/run', { push })
  await refreshMaster()
  return r
}

// ---------- 展示/登记 ----------
function dayOnly(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

export function dateDiffDays(dateStr) {
  const d = new Date(String(dateStr || '').replace(' ', 'T'))
  if (Number.isNaN(+d)) return null
  return Math.round((dayOnly(d) - dayOnly(new Date())) / 86400000)
}

export function relOf(dateStr) {
  const n = dateDiffDays(dateStr)
  if (n === null) return ''
  if (n < 0) return '已过'
  if (n === 0) return '今日'
  if (n === 1) return '明日'
  if (n === 2) return '后天'
  return `${n} 天后`
}

export const statusCls = { 已投: 'st-done', 在投: 'st-doing', 放弃: 'st-give' }

// 可登记的候选行（含未定开标时间的项目）
export function trackableRows() {
  if (bids.state === 'master') {
    return bids.rows.map((r) => ({
      name: r.name,
      date: r.open_at || '',
      status: r.status || '',
      unit: r.bidder || '',
    }))
  }
  return openingsView().map((o) => ({
    name: o.name,
    date: o.date,
    status: o.status || '',
    unit: o.unit || '',
  }))
}

// 未来 0~7 日开标列表（提醒模块/总览共用）
export function upcomingRows() {
  if (bids.state === 'master') {
    const out = bids.rows
      .filter((r) => {
        const n = r.open_at ? dateDiffDays(r.open_at) : null
        return n !== null && n >= 0 && n <= 7
      })
      .map((r) => ({
        id: 'm' + bids.rows.indexOf(r),
        name: r.name,
        date: r.open_at,
        rel: relOf(r.open_at),
        status: r.status || '',
        unit: r.bidder || '',
        keywords: r.keywords || [],
        registered: !!(r.status || r.bidder),
        remark: r.remark || '',
      }))
    return out.sort((a, b) => String(a.date).localeCompare(String(b.date)))
  }
  return openingsView()
    .map((o, i) => ({
      id: 'd' + i,
      name: o.name,
      date: o.date,
      rel: relOf(o.date),
      status: o.status || '',
      unit: o.unit || '',
      keywords: o.keywords || [],
      registered: !!o.registered,
      remark: o.note || '',
    }))
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
}

export function countRegistered() {
  if (bids.state === 'master') return bids.rows.filter((r) => r.status).length
  return demoState.registrations.length
}

// 状态登记（主表→后端写回；演示模式→本地）
export async function applyRegistration(rec) {
  if (bids.state === 'master') {
    await apiPost('/api/bids/master/update', {
      name: rec.name,
      status: rec.status,
      bidder: rec.unit || '',
      remark: rec.note || '',
    })
    await refreshMaster()
    return 'master'
  }
  registerProject(rec.name, rec.status, rec.unit, rec.note)
  return 'demo'
}

export async function clearRegistration(name) {
  if (bids.state === 'master') {
    await apiPost('/api/bids/master/update', { name, status: '', bidder: '', remark: '' })
    await refreshMaster()
    return
  }
  removeRegistration(name)
}

export const fmtDay = (s) => String(s || '').slice(5)
