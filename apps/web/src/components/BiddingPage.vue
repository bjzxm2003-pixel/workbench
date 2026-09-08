<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import BaseIcon from './BaseIcon.vue'
import AssistantCard from './AssistantCard.vue'
import {
  bids,
  loadHealth,
  refreshMaster,
  uploadPlan,
  previewSample,
  confirmPlan,
  dailyStatus,
  runDailyJob,
  trackableRows,
  upcomingRows,
  statusCls,
  applyRegistration,
  clearRegistration,
  fmtDay,
} from '../store/bids'
import { STATUS_OPTIONS } from '../store/demo'

const props = defineProps({
  assistants: { type: Array, required: true },
  accent: { type: String, default: 'cyan' },
  keywords: { type: Array, default: () => [] },
})

onMounted(async () => {
  await Promise.all([loadHealth().catch(() => null), refreshMaster()])
})

// ---------- 月计划筛选助手：上传 → 预检 → 确认 ----------
const file = ref(null)
const busy = ref('') // '' | 'parse' | 'confirm'
const err = ref('')
const preview = ref(null) // {token, summary, filename, preview}
const previewShown = ref(12)
const doPush = ref(true)
const done = ref(null) // confirm 结果

function pickFile(e) {
  const f = e.target.files && e.target.files[0]
  if (f) {
    file.value = f
    preview.value = null
    done.value = null
    err.value = ''
  }
}

async function runPreview(fn) {
  busy.value = 'parse'
  err.value = ''
  try {
    const r = await fn()
    if (!r.preview || !r.preview.length) {
      err.value = '未命中任何项目，请检查关键词或文件列名（需含“项目名称”）'
      return
    }
    preview.value = r
    previewShown.value = 12
    done.value = null
  } catch (e2) {
    err.value = String(e2.message || e2)
  } finally {
    busy.value = ''
  }
}

const onUpload = () => file.value && runPreview(() => uploadPlan(file.value))
const onSample = () => runPreview(previewSample)

async function onConfirm() {
  if (!preview.value) return
  busy.value = 'confirm'
  err.value = ''
  try {
    const r = await confirmPlan(preview.value.token, doPush.value)
    done.value = r
    preview.value = null
    file.value = null
  } catch (e2) {
    err.value = String(e2.message || e2)
  } finally {
    busy.value = ''
  }
}

const resetAll = () => {
  preview.value = null
  done.value = null
  file.value = null
  err.value = ''
}

// ---------- M2：日招标项目筛选助手 ----------
const dStatus = ref(null)
const dailyBusy = ref(false)
const dailyErr = ref('')
const dailyPush = ref(false)
const dailyResult = ref(null)

async function loadDailyStatus() {
  try {
    const s = await dailyStatus()
    dStatus.value = s
    dailyPush.value = !!s.sc
  } catch {
    /* 忽略 */
  }
}
onMounted(loadDailyStatus)

async function runDaily() {
  dailyBusy.value = true
  dailyErr.value = ''
  dailyResult.value = null
  try {
    dailyResult.value = await runDailyJob(dailyPush.value)
    loadDailyStatus()
  } catch (e2) {
    dailyErr.value = String(e2.message || e2)
  } finally {
    dailyBusy.value = false
  }
}

// ---------- 文字快捷登记（解析"项目 … 状态 投标单位"） ----------
const quickText = ref('')
const parseQuick = () => {
  let t = quickText.value.trim()
  if (!t) return
  let status = form.status
  for (const s of ['已投', '在投', '放弃']) {
    if (t.includes(s)) {
      status = s
      t = t.replace(s, ' ').replace(/\s+/g, ' ').trim()
      break
    }
  }
  const cands = candidates.value.filter((c) => t.includes(c.name) || c.name.includes(t))
  let name = ''
  if (cands.length) {
    name = cands.slice().sort((a, b) => b.name.length - a.name.length)[0].name
  }
  let unit = ''
  if (name) {
    unit = t.replace(name, ' ')
  } else {
    name = t
    unit = ''
  }
  unit = unit.replace(/投标单位|单位|[:：,，。、]/g, ' ').replace(/\s+/g, ' ').trim()
  form.name = name
  form.status = status
  form.unit = unit
  form.note = ''
  quickText.value = ''
  flash.value = `已填充：${name}（${status}${unit ? ' · ' + unit : ''}）→ 点「保存登记」写入主表`
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flash.value = ''), 4200)
}

// ---------- 开标提醒与状态登记 ----------
const rows = computed(() => upcomingRows())
const tomorrowRows = computed(() => rows.value.filter((r) => r.rel === '明日'))
const laterRows = computed(() => rows.value.filter((r) => r.rel !== '明日'))
const candidates = computed(() => trackableRows())

const form = reactive({ name: '', status: '在投', unit: '', note: '' })
const flash = ref('')
const flashErr = ref('')
let flashTimer = null

function pickName() {
  const found = candidates.value.find((c) => c.name === form.name)
  if (found) {
    form.status = found.status || '在投'
    form.unit = found.unit
  } else {
    form.status = '在投'
    form.unit = ''
  }
  form.note = ''
}

async function saveReg() {
  if (!form.name) return
  flashErr.value = ''
  try {
    await applyRegistration({
      name: form.name,
      status: form.status,
      unit: form.unit,
      note: form.note,
    })
    flash.value = `✓ 已登记：${form.name} → ${form.status}${form.unit ? '（' + form.unit + '）' : ''}`
    form.unit = ''
    form.note = ''
  } catch (e2) {
    flashErr.value = String(e2.message || e2)
  }
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => {
    flash.value = ''
    flashErr.value = ''
  }, 3600)
}

async function revoke(name) {
  try {
    await clearRegistration(name)
    flash.value = `已撤销登记：${name}`
  } catch (e2) {
    flashErr.value = String(e2.message || e2)
  }
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => {
    flash.value = ''
    flashErr.value = ''
  }, 3600)
}

const summary = computed(() => preview.value?.summary)
const isBusy = computed(() => !!busy.value)
const modeBadge = computed(() => {
  if (bids.state === 'master') {
    return { cls: 'ok', text: `主表 ${bids.rows.length} 项 · 更新于 ${bids.updated_at || '—'}` }
  }
  if (bids.state === 'error') return { cls: 'warn', text: '后端离线 · 演示模式' }
  return { cls: 'warn', text: '演示模式 · 上传月计划生成主表' }
})
</script>

<template>
  <div class="bid-body">
    <!-- 数据模式提示条 -->
    <div class="modebar">
      <span class="chip-mode" :class="modeBadge.cls"><i class="dot2"></i>{{ modeBadge.text }}</span>
      <span v-if="bids.state === 'master'" class="modebar-links">
        <a class="mini-link" :href="'/api/bids/master/file?format=xlsx'" download>下载 xlsx</a>
        <a class="mini-link" :href="'/api/bids/master/file?format=csv'" download>下载 csv</a>
      </span>
      <span v-else class="modebar-hint">演示数据不真实推送 · 主表为空或后端不可用时自动降级</span>
    </div>

    <!-- ① 月招标计划筛选助手（M1） -->
    <section class="rmodule">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">MONTHLY PLAN FILTER · M1 已接入</div>
          <h3 class="rm-title">① 月招标计划筛选助手</h3>
        </div>
        <span class="kw-strip">
          <span class="kw-label">关键词</span>
          <span v-for="k in bids.keywords.length ? bids.keywords : keywords" :key="k" class="tag">{{ k }}</span>
        </span>
      </div>

      <!-- 上传区 -->
      <div class="up-body" v-if="!preview && !done">
        <div class="up-drop">
          <input id="plan-file" type="file" accept=".xlsx,.xlsm,.csv,.pdf" hidden @change="pickFile" />
          <label for="plan-file" class="up-drop-box" :class="{ has: file }">
            <BaseIcon name="upload" :size="22" />
            <div class="up-t1">{{ file ? file.name : '点击选择月招标计划文件' }}</div>
            <div class="up-t2" v-if="!file">支持 xlsx / csv / 文本型 PDF · 自动识别“项目名称 / 预计发布公告时间”等表头</div>
            <div class="up-t2" v-else>已选择 · 可再次点击更换</div>
          </label>
        </div>
        <div class="up-actions">
          <button class="btn-primary" :disabled="isBusy || !file" @click="onUpload">
            <BaseIcon name="radar" :size="14" /> 开始筛查
          </button>
          <button class="btn-ghost" :disabled="isBusy" @click="onSample">用内置样例联调</button>
          <span v-if="busy === 'parse'" class="up-loading"><i class="spin"></i> 解析中…（文本 PDF 约 15 秒）</span>
          <span v-else-if="busy === 'confirm'" class="up-loading"><i class="spin"></i> 保存并推送中…</span>
        </div>
        <p v-if="err" class="up-err">{{ err }}</p>
      </div>

      <!-- 预检结果 -->
      <div v-else-if="preview" class="preview">
        <div class="pv-summary">
          <div class="pv-file"><BaseIcon name="upload" :size="13" /> {{ preview.filename }}</div>
          <div class="pv-chips">
            <span class="pv-chip">原始行 <b>{{ summary.raw }}</b></span>
            <span class="pv-chip hit">关键词命中 <b>{{ summary.matched }}</b></span>
            <span class="pv-chip dup">去重剔除 <b>{{ summary.dup_dropped }}</b></span>
            <span class="pv-chip final">生成 <b>{{ summary.final }}</b> 项</span>
          </div>
          <div class="pv-kw">
            <span v-for="(cnt, k) in summary.keyword_hits" :key="k" class="tag sm">{{ k }} × {{ cnt }}</span>
          </div>
        </div>
        <div v-if="bids.state === 'master'" class="pv-warn">⚠ 确认后将<b>覆盖</b>现有主表（{{ bids.rows.length }} 项）</div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>#</th><th>项目名称</th><th>预计发布公告时间</th><th>发布时间</th>
                <th>开标时间</th><th>投标单位</th><th>状态</th><th>命中</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in preview.preview.slice(0, previewShown)" :key="i">
                <td>{{ i + 1 }}</td>
                <td class="td-name" :title="r.name">{{ r.name }}</td>
                <td>{{ r.expect_publish || '—' }}</td>
                <td>{{ r.publish_at || '—' }}</td>
                <td>{{ r.open_at || '—' }}</td>
                <td>{{ r.bidder || '—' }}</td>
                <td>{{ r.status || '—' }}</td>
                <td><span v-for="k in r.keywords" :key="k" class="tag sm">{{ k }}</span></td>
              </tr>
            </tbody>
          </table>
          <div v-if="preview.preview.length > previewShown" class="pv-more">
            共 {{ preview.preview.length }} 项，仅展示前 {{ previewShown }} 条
            <button class="link-btn" @click="previewShown += 50">展开更多</button>
          </div>
        </div>
        <div class="pv-actions">
          <label class="chk">
            <input type="checkbox" v-model="doPush" />
            <span>确认后推送个人微信（Server酱）</span>
          </label>
          <span v-if="!bids.sc" class="sc-tip">未配置 SCKEY：填入 server/.env 后重启即可推送</span>
          <button class="btn-primary" :disabled="busy === 'confirm'" @click="onConfirm">
            <BaseIcon name="check" :size="14" /> 确认生成主表
          </button>
          <button class="btn-ghost" :disabled="busy === 'confirm'" @click="preview = null">返回</button>
        </div>
        <p v-if="err" class="up-err">{{ err }}</p>
      </div>

      <!-- 确认结果 -->
      <div v-else-if="done" class="done">
        <div class="done-icon"><BaseIcon name="check" :size="22" /></div>
        <div class="done-main">
          <div class="done-title">主表已生成 · {{ done.count }} 项</div>
          <div class="done-sub">导出：{{ done.exports.xlsx }} / {{ done.exports.csv }}（存于 data/bidding/exports/）</div>
          <div v-if="done.push" class="done-push">
            <template v-if="done.push.sent">✅ 已推送个人微信</template>
            <template v-else>⚠ 推送未发送：{{ done.push.reason }}</template>
          </div>
          <div class="done-actions">
            <a class="btn-ghost as-link" :href="'/api/bids/master/file?format=xlsx'" download>下载 xlsx</a>
            <a class="btn-ghost as-link" :href="'/api/bids/master/file?format=csv'" download>下载 csv</a>
            <button class="btn-ghost" @click="resetAll">继续上传</button>
          </div>
        </div>
      </div>
    </section>

    <!-- ② 日招标项目筛选助手（M2） -->
    <section class="rmodule">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">DAILY BIDDING FILTER · M2 已接入</div>
          <h3 class="rm-title">② 日招标项目筛选助手</h3>
        </div>
        <span class="rm-demo"><BaseIcon name="clock" :size="12" /> 每日 18:00 自动 · GH Actions</span>
      </div>
      <div class="daily-body">
        <div class="daily-status">
          <div class="ds-item"><span>调度</span><b>每日 18:00（北京）· 可随时手动运行</b></div>
          <div class="ds-item">
            <span>最近运行</span>
            <b v-if="dStatus && dStatus.last_run">{{ dStatus.last_run.date }} · 新增 {{ dStatus.last_run.summary.added }} / 补全 {{ dStatus.last_run.summary.updated }}（{{ dStatus.last_run.last_run }}）</b>
            <b v-else class="dim">尚未运行过</b>
          </div>
        </div>
        <div class="up-actions">
          <label class="chk"><input type="checkbox" v-model="dailyPush" /><span>运行后推送个人微信</span></label>
          <button class="btn-primary" :disabled="dailyBusy" @click="runDaily">
            <BaseIcon name="radar" :size="14" /> 立即运行一次
          </button>
          <span v-if="dailyBusy" class="up-loading"><i class="spin"></i> 抓取国能e招并合并主表…</span>
          <span v-if="!dStatus || !dStatus.sc" class="sc-tip">SCKEY 未配置，推送将跳过</span>
        </div>
        <p v-if="dailyErr" class="up-err">{{ dailyErr }}</p>

        <div v-if="dailyResult" class="pv-summary daily-result">
          <div class="pv-chips">
            <span class="pv-chip">当日公告 <b>{{ dailyResult.fresh }}</b></span>
            <span class="pv-chip hit">关键词命中 <b>{{ dailyResult.matched }}</b></span>
            <span class="pv-chip">历史已处理 <b>{{ dailyResult.history_skipped }}</b></span>
            <span class="pv-chip dup">新增并入 <b>{{ dailyResult.added }}</b></span>
            <span class="pv-chip">补全 <b>{{ dailyResult.updated }}</b></span>
            <span class="pv-chip final">主表共 <b>{{ dailyResult.master_total }}</b> 项</span>
          </div>
          <div v-if="dailyResult.push" class="pv-kw">
            <span class="tag">{{ dailyResult.push.sent ? '✅ 已推送个人微信' : '未推送：' + dailyResult.push.reason }}</span>
          </div>
          <ul v-if="dailyResult.added_items && dailyResult.added_items.length" class="mini-items">
            <li v-for="it in dailyResult.added_items.slice(0, 8)" :key="it.name">
              <a :href="it.url" target="_blank" rel="noreferrer">{{ it.name }}</a>
              <span class="rel-tag">发布 {{ it.publish_at }} · 开标 {{ it.open_at || '待定' }}</span>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- ③ 开标提醒与状态登记（真实主表 / 演示） -->
    <section class="rmodule">
      <div class="rm-head">
        <div class="rm-titles">
          <div class="rm-kicker">OPENING REMINDER · 状态登记</div>
          <h3 class="rm-title">③ 开标提醒与状态登记</h3>
        </div>
        <span class="rm-demo" :class="{ warn: bids.state !== 'master' }">
          <BaseIcon name="check" :size="12" />
          {{ bids.state === 'master' ? '数据源：主表' : 'DEMO 样例' }}
        </span>
      </div>

      <div class="reg-entry">
        <div class="reg-label-row">
          <span class="reg-label">状态登记入口</span>
          <span class="reg-tip">登记后同步用于 18:00 日招标更新与 09:00 明日开标提醒（M2/M3）</span>
        </div>
        <div class="reg-grid">
          <label class="fld fld-proj">
            <span>项目</span>
            <input v-model="form.name" list="cand-projects" placeholder="输入或选择项目名称…" @change="pickName" />
            <datalist id="cand-projects">
              <option v-for="c in candidates" :key="c.name" :value="c.name" />
            </datalist>
          </label>
          <div class="fld">
            <span>状态</span>
            <div class="seg">
              <button
                v-for="s in STATUS_OPTIONS"
                :key="s"
                type="button"
                :class="[{ on: form.status === s }, `on-${statusCls[s]}`]"
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
            <input v-model="form.note" placeholder="可选" />
          </label>
          <div class="fld fld-act">
            <button class="btn-primary" @click="saveReg"><BaseIcon name="check" :size="14" /> 保存登记</button>
          </div>
        </div>
        <div class="quickreg">
          <span class="qr-label">文字登记</span>
          <input
            v-model="quickText"
            placeholder='示例：织金公司锅炉燃气代燃油节能改造EPC项目公开招标项目（第3次）招标公告 已投 中国电建'
            @keyup.enter="parseQuick"
          />
          <button class="btn-ghost" type="button" @click="parseQuick">解析并填充</button>
        </div>
        <p v-if="flash" class="reg-flash">{{ flash }}</p>
        <p v-if="flashErr" class="reg-flash err">{{ flashErr }}</p>
      </div>

      <div class="rm-section">
        <div class="rm-sec-head">
          <span class="rm-sec-tag urgent">明日开标</span>
          <span class="rm-sec-count">{{ tomorrowRows.length }} 项 · 09:00 自动提醒（M3）</span>
        </div>
        <div v-if="tomorrowRows.length" class="open-list">
          <div v-for="r in tomorrowRows" :key="r.id" class="open-row urgent">
            <div class="open-time">
              <div class="open-day">{{ fmtDay(r.date) }}</div>
              <div class="open-hm">{{ String(r.date).slice(11) || '—' }}</div>
            </div>
            <div class="open-mid">
              <div class="open-name">{{ r.name }}</div>
              <div class="open-kw">
                <span v-for="k in r.keywords" :key="k" class="tag sm">{{ k }}</span>
                <span v-if="r.remark" class="rel-tag">备注：{{ r.remark }}</span>
              </div>
            </div>
            <div class="open-side">
              <span v-if="r.status" class="st" :class="statusCls[r.status]">{{ r.status }}</span>
              <span v-else class="st st-none">待登记</span>
              <span class="open-unit">{{ r.unit || '—' }}</span>
              <button v-if="r.registered" class="link-btn" @click="revoke(r.name)">撤销</button>
            </div>
          </div>
        </div>
        <div v-else class="rm-empty">近两日暂无开标项目</div>
      </div>

      <div v-if="laterRows.length" class="rm-section">
        <div class="rm-sec-head">
          <span class="rm-sec-tag">近 7 日</span>
          <span class="rm-sec-count">{{ laterRows.length }} 项</span>
        </div>
        <div class="open-list">
          <div v-for="r in laterRows" :key="r.id" class="open-row">
            <div class="open-time">
              <div class="open-day">{{ fmtDay(r.date) }}</div>
              <div class="open-hm">{{ String(r.date).slice(11) || '—' }}</div>
            </div>
            <div class="open-mid">
              <div class="open-name">{{ r.name }}</div>
              <div class="open-kw">
                <span v-for="k in r.keywords" :key="k" class="tag sm">{{ k }}</span>
                <span class="rel-tag">{{ r.rel }}</span>
                <span v-if="r.remark" class="rel-tag">备注：{{ r.remark }}</span>
              </div>
            </div>
            <div class="open-side">
              <span v-if="r.status" class="st" :class="statusCls[r.status]">{{ r.status }}</span>
              <span v-else class="st st-none">待登记</span>
              <span class="open-unit">{{ r.unit || '—' }}</span>
              <button v-if="r.registered" class="link-btn" @click="revoke(r.name)">撤销</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="bids.state !== 'master'" class="rm-footnote">
        当前为演示数据（项目名与开标时间均为样例）。上传月计划并确认后，此处自动切换为主表真实项目。
      </div>
    </section>

    <!-- ③ 自动化助手规划卡 -->
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
  </div>
</template>
