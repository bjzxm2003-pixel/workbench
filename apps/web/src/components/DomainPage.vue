<script setup>
import { computed } from 'vue'
import BaseIcon from './BaseIcon.vue'
import { keywordPresets } from '../data/modules'

const props = defineProps({
  domain: { type: Object, required: true },
})

const accentClass = computed(() => `accent-${props.domain.accent}`)
const stageNotes = {
  bid: 'M0 外壳就绪 · M1 月计划筛选（进行中）',
  silver: 'M0 外壳就绪 · M4 银发康养助手（待开发）',
  guoxue: 'M0 外壳就绪 · M5 国学助手（待开发）',
}
const keywords = computed(() => keywordPresets[props.domain.id] || [])
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div class="ph-icon" :class="accentClass"><BaseIcon :name="domain.icon" :size="22" /></div>
      <div>
        <div class="kicker" :class="`txt-${domain.accent}`">{{ domain.en }}</div>
        <h1>{{ domain.label }}</h1>
        <p class="page-desc">{{ domain.desc }}</p>
      </div>
      <div class="stage-pill">{{ stageNotes[domain.id] }}</div>
    </div>

    <div class="assistant-grid">
      <article
        v-for="(a, i) in domain.assistants"
        :key="a.id"
        class="card"
        :class="[accentClass, { first: i === 0 }]"
      >
        <div class="card-top">
          <span class="card-index">0{{ i + 1 }}</span>
          <span class="sched" :class="a.trigger">
            <BaseIcon name="clock" :size="13" />{{ a.schedule }}
          </span>
        </div>
        <h2 class="card-title">{{ a.name }}</h2>
        <div class="card-en">{{ a.en }}</div>
        <p class="card-desc">{{ a.desc }}</p>
        <div class="card-foot">
          <span class="tag" v-for="k in keywords.slice(0, 4)" :key="k">{{ k }}</span>
          <span class="progress">{{ a.progress }}</span>
        </div>
      </article>
    </div>

    <div class="placeholder">
      <div class="ph-inner">
        <div class="ph-title">
          <BaseIcon name="upload" :size="16" /> 里程碑施工中
        </div>
        <p>该业务域的功能将在后续里程碑（M1–M5）逐个接入。每个助手完成后会在此页面呈现真实数据与操作入口。</p>
      </div>
    </div>
  </section>
</template>
