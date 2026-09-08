// 演示数据层：投标"状态登记"的内存 + localStorage 存储。
// 开标列表始终由 buildDemoOpenings() 按当天动态构建；
// 登记记录按"项目名称"为键存储，展示时合并到对应项目行上。
// M1 接入真实招标主表与后端后，本文件由持久化 API 取代。

import { reactive } from 'vue'
import { buildDemoOpenings } from '../data/demo'

const KEY = 'wb.demo.registrations.v1'

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || []
  } catch {
    return []
  }
}

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(demoState.registrations))
  } catch {
    /* ignore */
  }
}

export const demoState = reactive({ registrations: load() })

export function registerProject(name, status, unit, note) {
  const rec = { name, status, unit: (unit || '').trim(), note: (note || '').trim(), ts: Date.now() }
  demoState.registrations = [
    ...demoState.registrations.filter((r) => r.name !== name),
    rec,
  ]
  persist()
}

export function removeRegistration(name) {
  demoState.registrations = demoState.registrations.filter((r) => r.name !== name)
  persist()
}

// 展示用：开标样例 + 已登记信息合并
export function openingsView() {
  return buildDemoOpenings().map((o) => {
    const r = demoState.registrations.find((x) => x.name === o.name)
    return r
      ? { ...o, status: r.status, unit: r.unit, note: r.note, registered: true }
      : { ...o, status: null, unit: '', note: '', registered: false }
  })
}

export const STATUS_OPTIONS = ['已投', '在投', '放弃']
