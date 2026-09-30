<script setup>
import { ref, onMounted } from 'vue'
import BaseIcon from './BaseIcon.vue'
import { apiGet } from '../api'

const items = ref([])
const count = ref(0)
const source = ref('')
const busy = ref(false)
const err = ref('')
const lastUpdate = ref('')

function fmtHot(n) {
  n = n || 0
  if (n >= 100000000) return (n / 100000000).toFixed(1) + ' 亿'
  if (n >= 10000) return (n / 10000).toFixed(1) + ' 万'
  return String(n)
}

async function load() {
  busy.value = true
  err.value = ''
  try {
    const r = await apiGet('/api/radar/list')
    items.value = r.items || []
    count.value = r.count || 0
    source.value = r.source || ''
    lastUpdate.value = new Date().toLocaleString('zh-CN', { hour12: false })
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div class="ph-icon accent-green"><BaseIcon name="radar" :size="22" /></div>
      <div>
        <div class="kicker txt-green">HOT RADAR · 选题灵感</div>
        <h1>热点雷达</h1>
        <p class="page-desc">
          借 Easel 热点雷达 · 聚合微博 / 抖音 / 知乎 / 头条 / 百度 / B站热榜，按国学·银发康养关键词筛选
        </p>
      </div>
      <div class="stage-pill" :class="source === 'content.json' ? 'ok' : 'warn'">
        {{ source === 'content.json' ? '已连接工作台' : '未连接' }}
      </div>
    </div>

    <div class="modebar">
      <span class="chip-mode" :class="count ? 'ok' : 'warn'">
        <i class="dot2"></i>命中 {{ count }} 条灵感
      </span>
      <span class="modebar-hint">数据来源：智能体工作台 content.json · topics.radar</span>
      <button class="mini-link" :disabled="busy" @click="load">
        <BaseIcon name="radar" :size="12" /> {{ busy ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <p v-if="err" class="up-err">{{ err }}</p>

    <div v-if="items.length" class="radar-grid">
      <a
        v-for="(it, i) in items"
        :key="it.id"
        class="radar-card"
        :href="it.url || '#'"
        target="_blank"
        rel="noopener"
      >
        <div class="rc-rank">{{ i + 1 }}</div>
        <div class="rc-main">
          <div class="rc-title">{{ it.title }}</div>
          <div class="rc-meta">
            <span class="rc-src">{{ it.source }}</span>
            <span class="rc-hot"><BaseIcon name="radar" :size="11" /> {{ fmtHot(it.hot) }}</span>
            <span v-if="it.note" class="rc-note">{{ it.note }}</span>
          </div>
          <div v-if="it.created" class="rc-date">{{ it.created }}</div>
        </div>
      </a>
    </div>

    <div v-else class="rm-empty">
      {{ err ? '加载失败，请检查后端是否运行' : '暂无灵感数据。运行 radar.py --board 生成后点「刷新」。' }}
    </div>
  </section>
</template>
