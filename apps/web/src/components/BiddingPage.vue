<script setup>
import { ref, computed } from 'vue'
import BaseIcon from './BaseIcon.vue'
import AssistantCard from './AssistantCard.vue'
import {
  demoState,
  registerProject,
  removeRegistration,
  openingsView,
  STATUS_OPTIONS,
} from '../store/demo'
import { relLabel } from '../data/demo'

const props = defineProps({
  assistants: { type: Array, required: true },
  accent: { type: String, default: 'cyan' },
  keywords: { type: Array, default: () => [] },
})

// ---------- 状态登记表单 ----------
const form = ref({ name: '', status: '在投', unit: '', note: '' })
const flash = ref('')
let flashTimer = null

const rows = computed(() =>
  openingsView().map((o) => ({ ...o, rel: relLabel(o.date) }))
)
const tomorrowRows = computed(() => rows.value.filter((r) => r.rel === '明日'))
const laterRows = computed(() => rows.value.filter((r) => r.rel !== '明日'))

function selectProject() {
  const rec = demoState.registrations.find((r) => r.name === form.value.name)
  if (rec) {
    form.value.status = rec.status
    form.value.unit = rec.unit
    form.value.note = rec.note
  } else {
    form.value.status = '在投'
    form.value.unit = ''
    form.value.note = ''
  }
}

function save() {
  if (!form.value.name) return
  registerProject(form.value.name, form.value.status, form.value.unit, form.value.note)
  flash.value = `✓ 已登记：${form.value.name} → ${form.value.status}${form.value.unit ? '（' + form.value.unit + '）' : ''}`
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flash.value = ''), 3200)
  form.value.unit = ''
  form.value.note = ''
}

const stCls = { 已投: 'st-done', 在投: 'st-doing', 放弃: 'st-give' }

function fmtDay(dateStr) {
  return dateStr.slice(5)
}
</script>

<template>
  <div class="bid-body">
    <!-- 三个自动化助手 -->
    <div class="assistant-grid">
      <AssistantCard
        v-for="(a, i) in assistants"
        :key="a.id"
        :assistant="a"
        :accent="accent"
        :keywords="keywords"
        :index="i"
      />
    </div>

    <!-- 开标提醒 · 状态登记 -->
    <section class="rmodule">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">OPENING REMINDER · 状态登记</div>
          <h3 class="rm-title">开标提醒与状态登记</h3>
        </div>
        <span class="rm-demo"><BaseIcon name="check" :size="12" /> DEMO · M1 接入真实主表</span>
      </div>

      <!-- 状态登记入口 -->
      <div class="reg-entry">
        <div class="reg-label-row">
          <span class="reg-label">状态登记入口</span>
          <span class="reg-tip">登记后同步用于 18:00 日招标更新与 09:00 明日开标提醒（M2/M3 接入）</span>
        </div>
        <div class="reg-grid">
          <label class="fld fld-proj">
            <span>项目</span>
            <select v-model="form.name" @change="selectProject">
              <option value="" disabled>选择项目…</option>
              <option v-for="r in rows" :key="r.id" :value="r.name">{{ r.name }}</option>
            </select>
          </label>

          <div class="fld">
            <span>状态</span>
            <div class="seg">
              <button
                v-for="s in STATUS_OPTIONS"
                :key="s"
                type="button"
                :class="[{ on: form.status === s }, `on-${stCls[s]}`]"
                @click="form.status = s"
              >
                {{ s }}
              </button>
            </div>
          </div>

          <label class="fld">
            <span>投标单位</span>
            <input v-model="form.unit" placeholder="如：中国电建" />
          </label>

          <label class="fld fld-note">
            <span>备注</span>
            <input v-model="form.note" placeholder="可选：如保证金/联系人" />
          </label>

          <div class="fld fld-act">
            <button class="btn-primary" @click="save">
              <BaseIcon name="check" :size="14" /> 保存登记
            </button>
          </div>
        </div>
        <p v-if="flash" class="reg-flash">{{ flash }}</p>
      </div>

      <!-- 提醒列表：明日开标 -->
      <div class="rm-section">
        <div class="rm-sec-head">
          <span class="rm-sec-tag urgent">明日开标</span>
          <span class="rm-sec-count">{{ tomorrowRows.length }} 项 · 09:00 自动提醒</span>
        </div>
        <div v-if="tomorrowRows.length" class="open-list">
          <div v-for="r in tomorrowRows" :key="r.id" class="open-row urgent">
            <div class="open-time">
              <div class="open-day">{{ fmtDay(r.date) }}</div>
              <div class="open-hm">{{ r.date.slice(11) }}</div>
            </div>
            <div class="open-mid">
              <div class="open-name">{{ r.name }}</div>
              <div class="open-kw">
                <span v-for="k in r.keywords" :key="k" class="tag">{{ k }}</span>
              </div>
            </div>
            <div class="open-side">
              <span v-if="r.status" class="st" :class="stCls[r.status]">{{ r.status }}</span>
              <span v-else class="st st-none">待登记</span>
              <span class="open-unit">{{ r.unit || '—' }}</span>
              <button v-if="r.registered" class="link-btn" @click="removeRegistration(r.name)">撤销</button>
            </div>
          </div>
        </div>
        <div v-else class="rm-empty">近两日暂无开标项目</div>
      </div>

      <!-- 提醒列表：后续近 7 日 -->
      <div class="rm-section" v-if="laterRows.length">
        <div class="rm-sec-head">
          <span class="rm-sec-tag">近 7 日</span>
          <span class="rm-sec-count">{{ laterRows.length }} 项</span>
        </div>
        <div class="open-list">
          <div v-for="r in laterRows" :key="r.id" class="open-row">
            <div class="open-time">
              <div class="open-day">{{ fmtDay(r.date) }}</div>
              <div class="open-hm">{{ r.date.slice(11) }}</div>
            </div>
            <div class="open-mid">
              <div class="open-name">{{ r.name }}</div>
              <div class="open-kw">
                <span v-for="k in r.keywords" :key="k" class="tag">{{ k }}</span>
                <span class="rel-tag">{{ r.rel }}</span>
              </div>
            </div>
            <div class="open-side">
              <span v-if="r.status" class="st" :class="stCls[r.status]">{{ r.status }}</span>
              <span v-else class="st st-none">待登记</span>
              <span class="open-unit">{{ r.unit || '—' }}</span>
              <button v-if="r.registered" class="link-btn" @click="removeRegistration(r.name)">撤销</button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
