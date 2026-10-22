<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { chatApi } from '../services/chatApi'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const health = ref(null), sessionId = ref(null), version = ref(0), state = ref({})
const turns = ref([]), sessions = ref([]), draft = ref(''), busy = ref(false), error = ref('')
const discoveries = ref([]), detail = ref(null), activeCard = ref(null), loginBusy = ref(false)
const feedbackState = ref({}), showTrace = ref(false), chatBottom = ref(null)
const suggestions = ['想看关于虚拟现实的科幻片，两小时以内，不要恐怖片', '来点轻松温暖的喜剧，不超过100分钟', '像《The Matrix》一样，关于现实与身份的电影']
const genreCN = { 'Sci-Fi':'科幻', Comedy:'喜剧', Horror:'恐怖', Mystery:'悬疑', Thriller:'惊悚', Animation:'动画', Romance:'爱情', Action:'动作', Adventure:'冒险', Fantasy:'奇幻', Crime:'犯罪', War:'战争', Documentary:'纪录', "Children's":'儿童', Drama:'剧情', Western:'西部' }
const last = computed(() => turns.value.at(-1)?.response)
const chips = computed(() => {
  const s = state.value, out = []
  if (s.runtime_max) out.push({ text:`≤ ${s.runtime_max} 分钟`, clear:'时长不限了' })
  if (s.year_min || s.year_max) out.push({ text:`${s.year_min || '不限'}—${s.year_max || '不限'}`, clear:'年份不限了' })
  if (s.include_genres?.length) out.push({ text:s.include_genres.map(g=>genreCN[g]||g).join(' · '), clear:'类型不限' })
  if (s.exclude_genres?.length) out.push({ text:'排除 '+s.exclude_genres.map(g=>genreCN[g]||g).join('、'), clear:'类型不限' })
  if (s.exclude_seen !== false) out.push({ text:'排除已看', clear:'看过的也可以' })
  return out
})
const modelLabel = computed(() => health.value?.parser_mode === 'llm' ? 'LLM 已连接' : '本地规则演示')
const preferenceLabel = computed(() => {
  const query = state.value.semantic_query || ''
  const themes = [['virtual reality','虚拟现实与身份'],['lighthearted','轻松愉快'],['heartwarming','温暖治愈'],['warmhearted','温暖治愈'],['space exploration','太空探索'],['robots','机器人'],['artificial intelligence','人工智能'],['coming of age','成长'],['friendship','友谊'],['family relationships','家庭关系'],['magic','魔法奇幻'],['time travel','时间旅行'],['dreams','梦境与现实'],['mind-bending','复杂叙事与悬念'],['uplifting','积极、有希望']]
  const labels = [...new Set(themes.filter(([term])=>query.includes(term)).map(([,label])=>label))]
  return labels.join(' · ') || query || '还没有设定。告诉我你想看的主题，或此刻的心情。'
})

function poster(id) { return `/api/posters/${id}.png` }
function imageFailed(event) { event.target.style.opacity='0' }
function storageKey() { return `cineweave-session-${auth.user?.user_id}` }
async function scrollBottom() { await nextTick(); chatBottom.value?.scrollIntoView({ behavior:'smooth', block:'end' }) }
async function refreshSessions() { if (auth.isAuthenticated) sessions.value = await chatApi.list() }

async function loginPersona(persona='demo') {
  loginBusy.value=true; error.value=''
  try {
    const data=await chatApi.login(`${persona}@cineweave.local`, 'CineweaveDemo!2026')
    localStorage.setItem('token', data.access_token); auth.token=data.access_token
    auth.user=await chatApi.profile(); localStorage.setItem('user', JSON.stringify(auth.user))
    sessionId.value=null; turns.value=[]; state.value={}; version.value=0
    await refreshSessions()
    const saved=localStorage.getItem(storageKey())
    if (saved) await restore(saved)
  } catch (e) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '暂时无法登录演示账号，请检查服务状态。' }
  finally { loginBusy.value=false }
}
async function newSession() {
  if (busy.value) return
  if (!auth.isAuthenticated) { await loginPersona(); if (!auth.isAuthenticated) return }
  const data=await chatApi.create(); sessionId.value=data.session_id; version.value=0
  state.value=data.active_constraints; turns.value=[]; error.value=''; feedbackState.value={}
  localStorage.setItem(storageKey(), sessionId.value); await refreshSessions()
}
async function restore(id) {
  if (busy.value) return
  try {
    const data=await chatApi.get(id)
    sessionId.value=id; turns.value=data.turns; version.value=data.state_version; state.value=data.active_constraints
    localStorage.setItem(storageKey(), id)
    await nextTick(); observeCards()
  } catch { localStorage.removeItem(storageKey()); sessionId.value=null; turns.value=[] }
}
async function send(text) {
  const message=(typeof text==='string' ? text : draft.value).trim()
  if (!message || busy.value) return
  if (!auth.isAuthenticated) { await loginPersona(); if (!auth.isAuthenticated) return }
  if (!sessionId.value) await newSession()
  busy.value=true; error.value=''; draft.value=''
  const entry={ message, response:null }; turns.value.push(entry); await scrollBottom()
  const body={ message, client_message_id:crypto.randomUUID(), expected_state_version:version.value, top_k:6 }
  try {
    const result=await chatApi.send(sessionId.value, body)
    entry.response=result; turns.value=[...turns.value]; version.value=result.state_version; state.value=result.active_constraints
    await refreshSessions(); await nextTick(); observeCards()
  } catch(e) {
    turns.value.pop()
    error.value=typeof e.response?.data?.detail==='string' ? e.response.data.detail : '本轮请求未完成，请稍后重试。'
    draft.value=message
    if (e.response?.status===409) { busy.value=false; await restore(sessionId.value) }
  } finally { busy.value=false; await scrollBottom() }
}
async function feedback(item, response, type) {
  if (!sessionId.value || busy.value) return
  try {
    const result=await chatApi.feedback(sessionId.value, { event_id:crypto.randomUUID(), request_id:response.request_id, movie_id:item.movie_id, feedback_type:type })
    version.value=result.state_version; feedbackState.value[`${response.request_id}-${item.movie_id}`]=type
    const latest=await chatApi.get(sessionId.value); state.value=latest.active_constraints
  } catch(e) { error.value=typeof e.response?.data?.detail==='string' ? e.response.data.detail : '反馈未保存，请重试。' }
}
function openDetail(item, response=null) {
  detail.value=item; activeCard.value=response
  if (response && sessionId.value) chatApi.event({ event_id:crypto.randomUUID(), session_id:sessionId.value,
    request_id:response.request_id, movie_id:item.movie_id, event_type:'movie_open' }).catch(()=>{})
}
const impressions=new Set()
let healthTimer
function observeCards() {
  const observer=new IntersectionObserver(entries=>{
    for (const entry of entries) if (entry.isIntersecting) {
      const { request, movie, session }=entry.target.dataset, key=`${session}-${request}-${movie}`
      if (request && session && !impressions.has(key)) {
        impressions.add(key)
        chatApi.event({ event_id:crypto.randomUUID(), session_id:session, request_id:request, movie_id:Number(movie), event_type:'impression' }).catch(()=>impressions.delete(key))
      }
      observer.unobserve(entry.target)
    }
  }, { threshold:0.4 })
  document.querySelectorAll('.cw-film[data-request]').forEach(el=>observer.observe(el))
}
onMounted(async()=>{
  try { health.value=await chatApi.health() } catch { error.value='后端暂不可用，请稍后刷新。' }
  try { discoveries.value=await chatApi.catalog() } catch {}
  if (!health.value?.ready) healthTimer=setInterval(async()=>{
    try {
      health.value=await chatApi.health()
      if(health.value.ready) {
        if(error.value==='后端暂不可用，请稍后刷新。') error.value=''
        if(!discoveries.value.length) discoveries.value=await chatApi.catalog()
        clearInterval(healthTimer)
      }
    } catch {}
  }, 15000)
  if (auth.isAuthenticated) {
    try { await refreshSessions(); const saved=localStorage.getItem(storageKey()); if(saved) await restore(saved) }
    catch(e) { if([401,403].includes(e.response?.status)) auth.logout() }
  }
})
onUnmounted(()=>clearInterval(healthTimer))
</script>

<template>
  <div class="cw-app">
    <aside class="cw-sidebar">
      <div class="cw-sidebar-heading">选片会话<small>保留每一次发现</small></div>
      <button class="cw-new" @click="newSession" :disabled="busy"><span>＋</span> 开始新的选片</button>
      <div class="cw-section-label">最近的选片 <span>{{ sessions.length }}</span></div>
      <div class="cw-session-list"><button v-for="s in sessions" :key="s.session_id" :class="{active:s.session_id===sessionId}" @click="restore(s.session_id)" :disabled="busy">{{ s.title }}</button><p v-if="!sessions.length">你的下一段电影旅程，<br>就从一句话开始。</p></div>
      <div class="cw-sidebar-bottom"><div class="cw-local"><i></i>{{ modelLabel }}</div><p>{{ health?.parser_mode==='llm' ? '理解你的表达，保留你的偏好。' : 'API 尚未配置，当前由规则解析条件。' }}</p><button @click="loginPersona(auth.user?.email?.startsWith('history')?'demo':'history')" :disabled="loginBusy || busy" class="cw-persona"><span class="cw-avatar">{{ auth.user?.email?.startsWith('history')?'影':'新' }}</span><span>{{ auth.user?.username || '本地演示访客' }}<small>{{ auth.user?.email?.startsWith('history')?'历史偏好已载入 · 点击切换':'点击体验有历史偏好的用户' }}</small></span><b>↔</b></button></div>
    </aside>

    <div class="cw-workspace">
      <header class="cw-topbar"><span>影织 <span class="cw-divider">/</span> <b>对话选片</b></span><div><button class="cw-mobile-new cw-text-button" @click="newSession" :disabled="busy">＋ 新会话</button><span class="cw-semantic-status" :class="{online:health?.semantic?.ready}"><i></i>{{ health?.semantic?.ready?'语义检索在线':'语义服务准备中' }}</span><button @click="showTrace=!showTrace" :aria-expanded="showTrace" class="cw-text-button">{{ showTrace?'收起':'查看' }}运行详情 ↗</button></div></header>
      <div class="cw-body" :class="{'cw-show-trace':showTrace}">
        <main class="cw-main">
          <section v-if="!turns.length" class="cw-welcome">
            <div class="cw-eyebrow"><span></span> 从电影库，找到你的下一部</div>
            <h1>找到今晚<em>想看的电影。</em></h1>
            <p class="cw-intro">说说此刻的心情，或一部念念不忘的电影。<br>我们一起，找到今晚的好故事。</p>
            <div class="cw-suggestions"><button v-for="(s,i) in suggestions" :key="s" @click="send(s)" :disabled="busy || loginBusy"><span>{{ ['◉','☀','⌘'][i] }}</span><div><b>{{ ['换一种现实','给生活一点暖意','沿着喜欢，继续发现'][i] }}</b><small>{{ s }}</small></div><span class="cw-arrow">↗</span></button></div>
            <div class="cw-discovery-head"><h2>先与这些故事见个面</h2><span>FROM THE COLLECTION</span></div>
            <div class="cw-discovery"><button v-for="(movie,i) in discoveries.slice(0,5)" :key="movie.movie_id" @click="openDetail(movie)" :style="{'--delay':i*70+'ms'}"><div class="cw-mini-poster"><img :src="poster(movie.movie_id)" :alt="movie.title" @error="imageFailed"><span>{{ String(i+1).padStart(2,'0') }}</span></div><b>{{ movie.title }}</b><small>{{ movie.year }} <span>★ {{ movie.imdb_rating || movie.avg_rating || '—' }}</span></small></button></div>
          </section>

          <div v-for="(turn,index) in turns" :key="index" class="cw-turn">
            <div class="cw-user-message"><span>你</span><p>{{ turn.message }}</p></div>
            <div class="cw-assistant-head"><span class="cw-symbol">✳</span><b>CineWeave</b><small>{{ modelLabel }}</small></div>
            <div v-if="!turn.response" class="cw-thinking"><span></span><span></span><span></span><p>正在理解条件、寻找电影并核对资料…</p></div>
            <template v-else>
              <p class="cw-reply">{{ turn.response.reply }}</p>
              <div v-if="turn.response.items.length" class="cw-film-grid">
                <article v-for="movie in turn.response.items" :key="movie.movie_id" class="cw-film" :data-movie="movie.movie_id" :data-request="turn.response.request_id" :data-session="sessionId">
                  <button class="cw-film-poster" @click="openDetail(movie,turn.response)"><img :src="poster(movie.movie_id)" :alt="movie.title" loading="lazy" @error="imageFailed"><span class="cw-film-number">{{ String(movie.final_rank || 1).padStart(2,'0') }}</span><span class="cw-rating">★ {{ movie.imdb_rating || '—' }}</span><span class="cw-poster-fallback">{{ movie.title }}</span></button>
                  <div class="cw-film-info"><button @click="openDetail(movie,turn.response)" class="cw-film-title">{{ movie.title }}</button><p>{{ movie.year || '年份未知' }} <span>·</span> {{ movie.runtime_minutes ? movie.runtime_minutes+' 分钟':'片长未知' }}</p><div class="cw-genres"><span v-for="g in movie.genres" :key="g">{{ genreCN[g]||g }}</span></div><p class="cw-reason">{{ movie.reason }}</p><div class="cw-film-actions"><button :class="{chosen:feedbackState[`${turn.response.request_id}-${movie.movie_id}`]==='like'}" @click="feedback(movie,turn.response,'like')" :disabled="busy">♡ 喜欢</button><button :class="{chosen:feedbackState[`${turn.response.request_id}-${movie.movie_id}`]==='seen'}" @click="feedback(movie,turn.response,'seen')" :disabled="busy">✓ 看过</button><button title="本次不感兴趣" @click="feedback(movie,turn.response,'dislike')" :disabled="busy">⊘</button></div></div>
                </article>
              </div>
              <div v-if="turn.response.items.length" class="cw-turn-footer"><span>✓ 电影与数值来自本地资料</span><span>{{ (turn.response.trace.total_ms/1000).toFixed(2) }} 秒 · {{ turn.response.trace.candidate_count || 0 }} 个候选</span></div>
            </template>
          </div>
          <div v-if="error" class="cw-error" role="alert">{{ error }}</div><div ref="chatBottom"></div>
          <div class="cw-composer-wrap"><div v-if="turns.length && chips.length" class="cw-active-chips"><button v-for="chip in chips" :key="chip.text" @click="send(chip.clear)" :disabled="busy">{{ chip.text }} <span>×</span></button></div><form class="cw-composer" @submit.prevent="send()"><textarea v-model="draft" rows="2" maxlength="1000" placeholder="今天，想看一个怎样的故事？" aria-label="描述你的选片需求" @keydown.enter.exact.prevent="send()" :disabled="busy"></textarea><div class="cw-composer-bottom"><span>◈ 说主题、心情，或继续调整条件</span><button type="submit" :disabled="busy || !draft.trim()" aria-label="发送选片需求">{{ busy?'…':'↑' }}</button></div></form><p class="cw-disclaimer">{{ modelLabel }} · 目录主要收录 2000 年及以前电影 · 推荐理由附资料依据</p></div>
        </main>

        <aside class="cw-context"><div class="cw-context-title"><span>◌</span><b>这一次，想看什么</b></div><p class="cw-context-caption">你的条件会留在当前会话里，<br>随时可以换个想法。</p><div class="cw-context-block"><label>本次偏好</label><p>{{ preferenceLabel }}</p></div><div class="cw-context-block"><label>筛选条件</label><div class="cw-context-tags"><span v-for="chip in chips" :key="chip.text">{{ chip.text }}</span><span v-if="!chips.length">尚未设置</span></div></div><div class="cw-context-block"><label>已排除电影</label><p>{{ state.excluded_movie_ids?.length || 0 }} 部 <small>仅作用于本次会话</small></p></div><button v-if="turns.length" class="cw-reset" @click="send('清空本次条件')" :disabled="busy">↺ 清空本次条件</button><div class="cw-note"><span>✳</span><p>好推荐，从理解你开始。<br><small>主题用语义匹配，时长与类型由资料核验。</small></p></div><div v-if="showTrace" class="cw-trace" aria-label="运行详情"><h3>运行详情</h3><p>意图：{{ modelLabel }}</p><p>模型：{{ health?.semantic?.manifest?.model || '未就绪' }}</p><p>目录：{{ health?.semantic?.manifest?.count || 0 }} 部</p><p v-if="last">状态：{{ last.status }}</p>
          <template v-if="last?.trace.orchestration">
            <p>编排：{{ last.trace.orchestration.backend }}</p>
            <ol class="cw-node-list"><li v-for="node in last.trace.orchestration.nodes" :key="node.node"><span>{{ node.node }}</span><small>{{ node.elapsed_ms }} ms</small></li></ol>
          </template><details v-if="last"><summary>完整运行数据</summary><pre>{{ JSON.stringify(last.trace,null,2) }}</pre></details><p v-else>发送一条选片需求后查看各阶段结果。</p></div></aside>
      </div>
    </div>

    <div v-if="detail" class="cw-modal-backdrop" @click.self="detail=null"><section class="cw-modal" role="dialog" aria-modal="true" :aria-label="detail.title"><button class="cw-modal-close" @click="detail=null" aria-label="关闭详情">×</button><div class="cw-modal-top"><img :src="poster(detail.movie_id)" :alt="detail.title" @error="imageFailed"><div><small>THE STORY BEHIND THE CHOICE</small><h2>{{ detail.title }}</h2><p>{{ detail.year || '年份未知' }} · {{ detail.runtime_minutes ? detail.runtime_minutes+' 分钟':'片长未知' }}</p><p>{{ (detail.genres || []).map(g=>genreCN[g]||g).join(' / ') }}</p><span>★ {{ detail.imdb_rating || '—' }} IMDb</span></div></div><h3>剧情资料</h3><p>{{ detail.description || '暂无简介，可前往电影库详情页查看已有资料。' }}</p><template v-if="detail.reason"><h3>为什么推荐给你</h3><p>{{ detail.reason }}</p><details><summary>查看事实依据</summary><pre>{{ JSON.stringify(detail.evidence,null,2) }}</pre></details></template><router-link :to="`/movie/${detail.movie_id}`" @click="detail=null" class="cw-detail-link">查看完整电影资料 ↗</router-link></section></div>
  </div>
</template>

<style scoped src="../assets/chat.css"></style>
