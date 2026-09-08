<script setup>
import { computed } from 'vue'
import BaseIcon from './BaseIcon.vue'
import { domains, overview, allTasks, scheduleMinutes } from '../data/modules'
import { openingsView, demoState } from '../store/demo'
import { relLabel } from '../data/demo'

defineEmits(['open'])

const tasks = computed(() =>
  allTasks()
    .slice()
    .sort((a, b) => scheduleMinutes(a.schedule) - scheduleMinutes(b.schedule))
)

const openings = computed(() => openingsView().map((o) => ({ ...o, rel: relLabel(o.date) })))
const tomorrowCount = computed(() => openings.value.filter((o) => o.rel === '明日').length)
const registeredCount = computed(() => demoState.registrations.length)
const todayGreet = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const todayDate = computed(() =>
  new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date())
)

const stats = computed(() => [
  { key: 'tasks', n: allTasks().length, label: '自动化助手', cap: 'M1 起分批接入', accent: 'cyan' },
  { key: 'open7', n: openings.value.length, label: '近 7 日开标', cap: '示例数据 · 实时计算', accent: 'violet' },
  { key: 'open1', n: tomorrowCount.value, label: '明日开标', cap: '09:00 推送提醒', accent: 'amber' },
  { key: 'reg', n: registeredCount.value, label: '状态已登记', cap: '投标单位/状态', accent: 'green' },
])

const dotCls = { bid: 'cyan', silver: 'violet', guoxue: 'amber' }
const statusCls = { 已投: 'st-done', 在投: 'st-doing', 放弃: 'st-give' }
const fmtDay = (s) => s.slice(5)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div class="ph-icon accent-cyan"><BaseIcon :name="overview.icon" :size="22" /></div>
      <div>
        <div class="kicker txt-cyan">{{ overview.en }}</div>
        <h1>{{ overview.label }}</h1>
        <p class="page-desc">{{ todayGreet }} · {{ todayDate }}，今日要务如下</p>
      </div>
      <div class="stage-pill">M0 · 界面预览中</div>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid">
      <div v-for="s in stats" :key="s.key" class="stat" :class="`accent-${s.accent}`">
        <div class="stat-n">{{ s.n }}</div>
        <div class="stat-label">{{ s.label }}</div>
        <div class="stat-cap">{{ s.cap }}</div>
      </div>
    </div>

    <div class="ov-cols">
      <!-- 今日自动化任务 -->
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title"><BaseIcon name="clock" :size="15" /> 今日自动化任务</div>
          <span class="panel-note">GitHub Actions · 北京时间</span>
        </div>
        <ul class="tl">
          <li v-for="t in tasks" :key="t.id" class="tl-row" @click="$emit('open', t.domainId)">
            <span class="tl-time">{{ t.schedule }}</span>
            <span class="tl-dot" :class="`dot-${dotCls[t.domainId]}`"></span>
            <div class="tl-mid">
              <div class="tl-name">{{ t.name }}</div>
              <div class="tl-domain">{{ t.domainLabel }} · {{ t.en }}</div>
            </div>
            <span class="chipprogress">{{ t.progress }}</span>
          </li>
        </ul>
      </div>

      <!-- 未来 7 日开标 -->
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title"><BaseIcon name="radar" :size="15" /> 未来 7 日开标</div>
          <button class="mini-link" @click="$emit('open', 'bid')">前往投标业务 <BaseIcon name="arrow" :size="12" /></button>
        </div>
        <ul v-if="openings.length" class="open-mini">
          <li v-for="o in openings" :key="o.id" class="open-mini-row" @click="$emit('open', 'bid')">
            <span class="om-date">
              <span class="om-day">{{ fmtDay(o.date) }}</span>
              <span class="om-rel" :class="{ urgent: o.rel === '明日' }">{{ o.rel }}</span>
            </span>
            <span class="om-name">{{ o.name }}</span>
            <span class="om-side">
              <span v-if="o.status" class="st" :class="statusCls[o.status]">{{ o.status }}</span>
              <span v-else class="st st-none">待登记</span>
            </span>
          </li>
        </ul>
        <div v-else class="rm-empty">暂无开标安排</div>
      </div>
    </div>

    <!-- 业务域快捷入口 -->
    <div class="sc-grid">
      <button
        v-for="d in domains"
        :key="d.id"
        class="sc-card"
        :class="`accent-${d.accent}`"
        @click="$emit('open', d.id)"
      >
        <span class="sc-icon"><BaseIcon :name="d.icon" :size="20" /></span>
        <span class="sc-body">
          <span class="sc-label">{{ d.label }}</span>
          <span class="sc-en">{{ d.en }}</span>
          <span class="sc-desc">{{ d.desc }}</span>
        </span>
        <span class="sc-count">{{ d.assistants.length }} 助手</span>
        <BaseIcon class="sc-arrow" name="arrow" :size="14" />
      </button>
    </div>
  </section>
</template>
