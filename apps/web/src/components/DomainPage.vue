<script setup>
import { computed } from 'vue'
import BaseIcon from './BaseIcon.vue'
import AssistantCard from './AssistantCard.vue'
import BiddingPage from './BiddingPage.vue'
import { keywordPresets } from '../data/modules'

const props = defineProps({
  domain: { type: Object, required: true },
})

const accentClass = computed(() => `accent-${props.domain.accent}`)
const keywords = computed(() => keywordPresets[props.domain.id] || [])
const stageNotes = {
  bid: 'M1 月计划筛选已接入 · M2/M3 待开发',
  silver: 'M0 外壳就绪 · M4 银发康养助手（待开发）',
  guoxue: 'M0 外壳就绪 · M5 国学助手（待开发）',
}
</script>

<template>
  <section class="page">
    <!-- 页头 -->
    <div class="page-head">
      <div class="ph-icon" :class="accentClass">
        <BaseIcon :name="domain.icon" :size="22" />
      </div>
      <div>
        <div class="kicker" :class="`txt-${domain.accent}`">{{ domain.en }}</div>
        <h1>{{ domain.label }}</h1>
        <p class="page-desc">{{ domain.desc }}</p>
      </div>
      <div class="stage-pill">{{ stageNotes[domain.id] }}</div>
    </div>

    <!-- 投标业务：三助手卡片 + 提醒模块（含状态登记） -->
    <BiddingPage
      v-if="domain.id === 'bid'"
      :assistants="domain.assistants"
      :accent="domain.accent"
      :keywords="keywords"
    />

    <!-- 银发康养 / 国学自媒体：通用助手卡片 -->
    <template v-else>
      <div class="assistant-grid">
        <AssistantCard
          v-for="(a, i) in domain.assistants"
          :key="a.id"
          :assistant="a"
          :accent="domain.accent"
          :keywords="keywords"
          :index="i"
        />
      </div>
      <div class="placeholder">
        <div class="ph-inner">
          <div class="ph-title"><BaseIcon name="upload" :size="16" /> 里程碑施工中</div>
          <p>该业务域的功能将在后续里程碑（M4/M5）接入。每个助手完成后会在此页面呈现真实数据与操作入口。</p>
        </div>
      </div>
    </template>
  </section>
</template>
