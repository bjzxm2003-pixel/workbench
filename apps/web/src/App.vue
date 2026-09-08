<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { domains, overview } from './data/modules'
import BaseIcon from './components/BaseIcon.vue'
import OverviewPage from './components/OverviewPage.vue'
import DomainPage from './components/DomainPage.vue'

// 导航顺序：今日总览置顶，随后三个业务域
const navItems = [overview, ...domains]
const active = ref('overview')
const now = ref(new Date())

let timer = null
onMounted(() => {
  timer = setInterval(() => (now.value = new Date()), 1000)
})
onUnmounted(() => clearInterval(timer))

const fmt = (t, opt) =>
  new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', ...opt }).format(t)

const clock = computed(() => fmt(now.value, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }))
const date = computed(() => fmt(now.value, { year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short' }))

const activeItem = computed(() => navItems.find((d) => d.id === active.value))
const accentTxt = computed(() => `txt-${activeItem.value?.accent || 'cyan'}`)
</script>

<template>
  <div class="shell">
    <!-- 左侧导航 -->
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><BaseIcon name="bolt" :size="20" /></div>
        <div class="brand-text">
          <div class="brand-title">个人工作台</div>
          <div class="brand-sub">DARK&nbsp;TECH&nbsp;·&nbsp;v0.1</div>
        </div>
      </div>

      <nav class="nav">
        <div class="nav-caption">NAVIGATION</div>
        <button
          v-for="d in navItems"
          :key="d.id"
          class="nav-item"
          :class="{ active: active === d.id, [`accent-${d.accent}`]: true }"
          @click="active = d.id"
        >
          <span class="nav-icon"><BaseIcon :name="d.icon" :size="18" /></span>
          <span class="nav-body">
            <span class="nav-label">{{ d.label }}</span>
            <span class="nav-en">{{ d.en }}</span>
          </span>
          <span v-if="d.assistants" class="nav-count">{{ d.assistants.length }}</span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <div class="chip">GH&nbsp;Actions</div>
        <div class="chip">Server酱</div>
        <div class="chip">DeepSeek</div>
        <div class="note">定时任务 · 每日自动运行</div>
      </div>
    </aside>

    <!-- 右侧主区 -->
    <div class="main">
      <header class="topbar">
        <div class="crumb">
          <span class="crumb-root">个人工作台</span>
          <span class="crumb-sep">/</span>
          <span class="crumb-cur" :class="accentTxt">{{ activeItem?.label }}</span>
        </div>
        <div class="top-right">
          <div class="status"><i class="dot"></i>系统在线</div>
          <div class="clock">
            <div class="clock-time">{{ clock }}</div>
            <div class="clock-date">{{ date }}</div>
          </div>
        </div>
      </header>

      <main class="content">
        <OverviewPage v-if="active === 'overview'" @open="active = $event" />
        <DomainPage v-else :domain="activeItem" />
      </main>
    </div>
  </div>
</template>
