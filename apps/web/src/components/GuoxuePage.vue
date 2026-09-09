<script setup>
import { ref, onMounted } from 'vue'
import BaseIcon from './BaseIcon.vue'
import { apiGet, apiPost } from '../api'

const state = ref(null)
const vBusy = ref(false)
const vErr = ref('')
const videoInfo = ref(null)
const busy = ref(false)
const err = ref('')
const pushOn = ref(false)
const reportMd = ref('')
const reportDate = ref('')

async function loadStatus() {
  try {
    state.value = await apiGet('/api/jobs/guoxue/status')
    pushOn.value = !!(state.value && state.value.sc)
    if (state.value && state.value.last_run && state.value.last_run.date) {
      await loadReport(state.value.last_run.date)
    }
  } catch {
    /* 忽略 */
  }
}

async function loadReport(date) {
  try {
    const r = await apiGet('/api/jobs/guoxue/report?date=' + encodeURIComponent(date))
    reportMd.value = r.markdown || ''
    reportDate.value = date
  } catch {
    reportMd.value = ''
  }
}

async function makeVideo() {
  vBusy.value = true
  vErr.value = ''
  videoInfo.value = null
  try {
    videoInfo.value = await apiPost('/api/jobs/guoxue/video', { date: reportDate.value || undefined })
  } catch (e2) {
    vErr.value = String(e2.message || e2)
  } finally {
    vBusy.value = false
  }
}

async function run() {
  busy.value = true
  err.value = ''
  try {
    const r = await apiPost('/api/jobs/guoxue/run', { push: pushOn.value })
    state.value = { ...(state.value || {}), last_run: r }
    await loadReport(r.date)
  } catch (e2) {
    err.value = String(e2.message || e2)
  } finally {
    busy.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="silver-body">
    <div class="modebar">
      <span class="chip-mode" :class="state && state.llm ? 'ok' : 'warn'">
        <i class="dot2"></i>{{ state && state.llm ? 'DeepSeek 已配置' : 'DeepSeek 未配置（server/.env）' }}
      </span>
      <span class="chip-mode" :class="state && state.sc ? 'ok' : 'warn'">
        <i class="dot2"></i>{{ state && state.sc ? 'Server酱 已配置' : 'Server酱 未配置' }}
      </span>
      <span class="modebar-hint">调度：每日 16:00（GH Actions）· 也可手动生成</span>
    </div>

    <section class="rmodule">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">GUOXUE SHORT-VIDEO · M5 已接入</div>
          <h3 class="rm-title">国学经典爆款短视频拆解与改编（抖音/快手）</h3>
        </div>
        <span class="rm-demo" :class="{ warn: !state || !state.llm }">
          <BaseIcon name="check" :size="12" /> 16:00 自动 · 拆解+改编脚本
        </span>
      </div>

      <div class="daily-body">
        <div class="daily-status">
          <div class="ds-item"><span>关键词</span><b>{{ (state && state.keywords ? state.keywords : ['国学', '易经', '道德经', '黄帝内经', '论语', '人生智慧']).join(' · ') }}</b></div>
          <div class="ds-item">
            <span>最近运行</span>
            <b v-if="state && state.last_run">
              {{ state.last_run.date }} · 候选 {{ state.last_run.candidates }} ·
              {{ state.last_run.push && state.last_run.push.sent ? '已推送微信' : '未推送' }}
            </b>
            <b v-else class="dim">尚未运行</b>
          </div>
        </div>

        <div class="up-actions">
          <label class="chk"><input type="checkbox" v-model="pushOn" /><span>生成后推送个人微信（Top3+改编稿摘要）</span></label>
          <button class="btn-primary" :disabled="busy || !state || !state.llm" @click="run">
            <BaseIcon name="radar" :size="14" /> 立即生成今日日报
          </button>
          <span v-if="busy" class="up-loading"><i class="spin"></i> LLM 选题+拆解+脚本创作中（约 1 分钟）…</span>
        </div>
        <p v-if="err" class="up-err">{{ err }}</p>

        <div v-if="state && state.last_run" class="top3-strip">
          <span class="tt">今日 Top3：</span>
          <span v-for="(t, i) in state.last_run.top3" :key="i" class="tt-item">
            {{ i + 1 }}.《{{ t.title }}》<em>{{ t.platform }} · {{ t.type }}</em>
          </span>
        </div>
      </div>
    </section>

    <section v-if="reportMd" class="rmodule report-panel">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">LATEST REPORT · {{ reportDate }}</div>
          <h3 class="rm-title">最近一期日报（Markdown 原文）</h3>
        </div>
        <span class="rm-demo">文件：data/media/reports/guoxue_{{ reportDate }}.md</span>
      </div>
      <pre class="md-view">{{ reportMd }}</pre>
    </section>

    <section v-if="state && state.last_run && state.last_run.date" class="rmodule">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">ONE-CLICK VIDEO · M5.1</div>
          <h3 class="rm-title">🎬 一键成片（配音 + 画面 + 字幕）</h3>
        </div>
        <span class="rm-demo">水墨风 · 竖屏 1080x1920 · Yunjian 磁性男声 · 按分镜时长</span>
      </div>
      <div class="daily-body">
        <div class="up-actions">
          <button class="btn-primary" :disabled="vBusy" @click="makeVideo">
            <BaseIcon name="radar" :size="14" /> 开始成片
          </button>
          <span v-if="vBusy" class="up-loading"><i class="spin"></i> 配音+画面合成中（约 1-2 分钟）…</span>
          <span v-else-if="videoInfo" class="up-loading">✅ 完成：{{ videoInfo.duration_s }}s · {{ videoInfo.segments }} 镜 · {{ (videoInfo.bytes / 1048576).toFixed(1) }}MB</span>
        </div>
        <p v-if="vErr" class="up-err">{{ vErr }}</p>
        <div v-if="videoInfo" class="done-actions" style="margin-top:12px">
          <a class="btn-ghost as-link" :href="'/api/jobs/guoxue/video-file?date=' + videoInfo.date + '&kind=mp4'" download>⬇ 下载 MP4（发抖音）</a>
          <a class="btn-ghost as-link" :href="'/api/jobs/guoxue/video-file?date=' + videoInfo.date + '&kind=cover'" download>⬇ 封面 PNG</a>
          <a class="btn-ghost as-link" :href="'/api/jobs/guoxue/video-file?date=' + videoInfo.date + '&kind=srt'" download>⬇ 字幕 SRT</a>
        </div>
        <p class="modebar-hint" style="margin-top:8px">提示：想要背景音乐，把 mp3 放到 <b>data/media/bgm.mp3</b> 再点成片即可自动混音；音色/版式可继续定制。</p>
      </div>
    </section>
  </div>
</template>
