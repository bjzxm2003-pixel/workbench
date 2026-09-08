<script setup>
import BaseIcon from './BaseIcon.vue'

defineProps({
  assistant: { type: Object, required: true },
  accent: { type: String, default: 'cyan' },
  keywords: { type: Array, default: () => [] },
  index: { type: Number, default: 0 },
})
</script>

<template>
  <article class="card" :class="[`accent-${accent}`]">
    <div class="card-top">
      <span class="card-index">0{{ index + 1 }}</span>
      <span class="sched" :class="assistant.trigger">
        <BaseIcon name="clock" :size="13" />{{ assistant.schedule }}
      </span>
    </div>
    <h2 class="card-title">{{ assistant.name }}</h2>
    <div class="card-en">{{ assistant.en }}</div>
    <p class="card-desc">{{ assistant.desc }}</p>
    <div class="card-foot">
      <span class="tag" v-for="k in keywords.slice(0, 4)" :key="k">{{ k }}</span>
      <span class="progress">{{ assistant.progress }}</span>
    </div>
  </article>
</template>
