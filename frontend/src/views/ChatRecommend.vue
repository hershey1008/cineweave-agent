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
      <a class="cw-brand" href="/" aria-label="CineWeave 首页"><span class="cw-symbol">✳</span><span>CineWeave<small>影织 · 让好电影与你相遇</small></span></a>
      <button class="cw-new" @click="newSession" :disabled="busy"><span>＋</span> 开始新的选片</button>
      <nav class="cw-nav"><span class="cw-nav-active">◈ <span>对话选片</span><small>精选</small></span><router-link to="/browse">▦ <span>探索电影库</span></router-link></nav>
      <div class="cw-section-label">最近的选片 <span>{{ sessions.length }}</span></div>
      <div class="cw-session-list"><button v-for="s in sessions" :key="s.session_id" :class="{active:s.session_id===sessionId}" @click="restore(s.session_id)" :disabled="busy">{{ s.title }}</button><p v-if="!sessions.length">你的下一段电影旅程，<br>就从一句话开始。</p></div>
      <div class="cw-sidebar-bottom"><div class="cw-local"><i></i>{{ modelLabel }}</div><p>{{ health?.parser_mode==='llm' ? '理解你的表达，保留你的偏好。' : 'API 尚未配置，当前由规则解析条件。' }}</p><button @click="loginPersona(auth.user?.email?.startsWith('history')?'demo':'history')" :disabled="loginBusy || busy" class="cw-persona"><span class="cw-avatar">{{ auth.user?.email?.startsWith('history')?'影':'新' }}</span><span>{{ auth.user?.username || '本地演示访客' }}<small>{{ auth.user?.email?.startsWith('history')?'历史偏好已载入 · 点击切换':'点击体验有历史偏好的用户' }}</small></span><b>↔</b></button></div>
    </aside>

    <div class="cw-workspace">
      <header class="cw-topbar"><span>你的私人选片室 <span class="cw-divider">/</span> <b>对话选片</b></span><div><span class="cw-semantic-status" :class="{online:health?.semantic?.ready}"><i></i>{{ health?.semantic?.ready?'语义检索在线':'语义服务准备中' }}</span><button @click="showTrace=!showTrace" class="cw-text-button">{{ showTrace?'收起':'查看' }}运行详情 ↗</button></div></header>
      <div class="cw-body">
        <main class="cw-main">
          <section v-if="!turns.length" class="cw-welcome">
            <div class="cw-eyebrow"><span></span> A LITTLE CONVERSATION, A GREAT FILM.</div>
            <h1>下一部，<br><em>值得期待。</em></h1>
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

        <aside class="cw-context"><div class="cw-context-title"><span>◌</span><b>这一次，想看什么</b></div><p class="cw-context-caption">你的条件会留在当前会话里，<br>随时可以换个想法。</p><div class="cw-context-block"><label>本次偏好</label><p>{{ preferenceLabel }}</p></div><div class="cw-context-block"><label>筛选条件</label><div class="cw-context-tags"><span v-for="chip in chips" :key="chip.text">{{ chip.text }}</span><span v-if="!chips.length">尚未设置</span></div></div><div class="cw-context-block"><label>已排除电影</label><p>{{ state.excluded_movie_ids?.length || 0 }} 部 <small>仅作用于本次会话</small></p></div><button v-if="turns.length" class="cw-reset" @click="send('清空本次条件')" :disabled="busy">↺ 清空本次条件</button><div class="cw-note"><span>✳</span><p>好推荐，从理解你开始。<br><small>主题用语义匹配，时长与类型由资料核验。</small></p></div><div v-if="showTrace" class="cw-trace"><h3>运行详情</h3><p>意图：{{ modelLabel }}</p><p>模型：{{ health?.semantic?.manifest?.model || '未就绪' }}</p><p>目录：{{ health?.semantic?.manifest?.count || 0 }} 部</p><p v-if="last">状态：{{ last.status }}</p><pre v-if="last">{{ JSON.stringify(last.trace,null,2) }}</pre><p v-else>发送一条选片需求后查看各阶段结果。</p></div></aside>
      </div>
    </div>

    <div v-if="detail" class="cw-modal-backdrop" @click.self="detail=null"><section class="cw-modal" role="dialog" aria-modal="true" :aria-label="detail.title"><button class="cw-modal-close" @click="detail=null" aria-label="关闭详情">×</button><div class="cw-modal-top"><img :src="poster(detail.movie_id)" :alt="detail.title" @error="imageFailed"><div><small>THE STORY BEHIND THE CHOICE</small><h2>{{ detail.title }}</h2><p>{{ detail.year || '年份未知' }} · {{ detail.runtime_minutes ? detail.runtime_minutes+' 分钟':'片长未知' }}</p><p>{{ (detail.genres || []).map(g=>genreCN[g]||g).join(' / ') }}</p><span>★ {{ detail.imdb_rating || '—' }} IMDb</span></div></div><h3>剧情资料</h3><p>{{ detail.description || '暂无简介，可前往电影库详情页查看已有资料。' }}</p><template v-if="detail.reason"><h3>为什么推荐给你</h3><p>{{ detail.reason }}</p><details><summary>查看事实依据</summary><pre>{{ JSON.stringify(detail.evidence,null,2) }}</pre></details></template><router-link :to="`/movie/${detail.movie_id}`" @click="detail=null" class="cw-detail-link">查看完整电影资料 ↗</router-link></section></div>
  </div>
</template>

<style scoped>
.cw-app{--bg:#f8f7f4;--ink:#252c2a;--muted:#7b827d;--line:#e7e7df;--accent:#bd583c;display:flex;min-height:100vh;background:var(--bg);color:var(--ink);font-family:Inter,'Segoe UI','Microsoft YaHei',sans-serif;font-size:14px}.cw-app button,.cw-app textarea{font:inherit}.cw-app button{cursor:pointer}.cw-app button:disabled{cursor:wait;opacity:.5}.cw-sidebar{position:fixed;inset:0 auto 0 0;width:242px;padding:32px 22px 20px;background:#eeeee7;border-right:1px solid #e2e3da;display:flex;flex-direction:column;z-index:20}.cw-brand{display:flex;gap:9px;align-items:center;color:#283b32;font-size:24px;font-weight:650;letter-spacing:-1px;text-decoration:none}.cw-symbol{font-size:33px;color:var(--accent);line-height:1}.cw-brand small{display:block;font-size:10px;font-weight:400;letter-spacing:.9px;color:#7d847b;margin-top:6px}.cw-new{margin-top:37px;border:1px solid #c8cfc1;background:#f8f9f3;border-radius:9px;padding:12px;text-align:left;color:#334d3d;font-weight:600!important;display:flex;gap:13px;align-items:center}.cw-new span{font-size:22px;line-height:1}.cw-nav{display:flex;flex-direction:column;gap:9px;margin:28px 0 35px}.cw-nav>a,.cw-nav>span{display:flex;gap:12px;align-items:center;padding:11px 12px;border-radius:7px;text-decoration:none;color:#697267}.cw-nav-active{background:#e2e6d9;color:#314b38!important}.cw-nav small{margin-left:auto;color:#738469;font-size:10px}.cw-section-label{font-size:10px;color:#8e968a;letter-spacing:1.6px;display:flex;justify-content:space-between;padding:0 11px}.cw-section-label span{letter-spacing:0}.cw-session-list{flex:1;min-height:30px;overflow:auto;margin-top:13px}.cw-session-list button{display:block;width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:none;border:0;padding:11px;border-radius:6px;color:#72796e;text-align:left;font-size:12px}.cw-session-list button.active{background:#e4e5dc;color:#3e4b3d}.cw-session-list p{padding:14px 11px;line-height:1.9;color:#a0a597;font-size:12px}.cw-sidebar-bottom{padding-top:18px;border-top:1px solid #dfe2d6}.cw-local{display:flex;gap:7px;align-items:center;font-size:11px;color:#67735f}.cw-local i,.cw-semantic-status i{width:6px;height:6px;border-radius:50%;background:#a4a898;display:inline-block}.cw-sidebar-bottom>p{color:#929887;font-size:10px;line-height:1.8;margin:8px 0 20px}.cw-persona{display:flex;align-items:center;gap:9px;border:0;background:none;text-align:left;width:100%;padding:0;color:#485740}.cw-avatar{border-radius:50%;background:#d7dfc7;width:32px;height:32px;display:grid;place-items:center;font-size:12px}.cw-persona small{display:block;font-size:9px;margin-top:4px;color:#8c9582}.cw-persona b{margin-left:auto;font-size:16px}.cw-workspace{margin-left:242px;flex:1;min-width:0}.cw-topbar{height:76px;border-bottom:1px solid var(--line);padding:0 34px;display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#8a9088;background:rgba(248,247,244,.96);position:sticky;top:0;z-index:10}.cw-topbar b{font-weight:500;color:#4e584e}.cw-divider{padding:0 14px;color:#c6c8be}.cw-topbar>div{display:flex;align-items:center;gap:22px}.cw-semantic-status{display:flex;align-items:center;gap:6px;font-size:10px}.cw-semantic-status.online i{background:#6f8760}.cw-text-button{border:0;background:none;color:#747d70;font-size:10px!important}.cw-body{display:flex;max-width:1580px;margin:auto}.cw-main{flex:1;min-width:0;padding:42px 5% 0}.cw-welcome{max-width:850px;margin:0 auto}.cw-eyebrow{display:flex;align-items:center;gap:8px;font-size:9px;letter-spacing:2.2px;color:#83917d;margin:8px 0 25px}.cw-eyebrow>span{width:19px;height:1px;background:#9fae92}.cw-welcome h1{font-family:Georgia,'Noto Serif SC','Songti SC','SimSun',serif;font-size:clamp(40px,4.5vw,68px);font-weight:400;line-height:1.35;letter-spacing:2px;margin:0}.cw-welcome h1 em{font-style:normal;color:#b45c43}.cw-intro{color:#8b9086;line-height:2;font-size:12px;margin:22px 0 28px}.cw-suggestions{display:flex;flex-direction:column;gap:9px}.cw-suggestions button{background:#fdfcf8;border:1px solid #e3e5d9;border-radius:8px;padding:14px 16px;display:flex;gap:13px;text-align:left;align-items:center;transition:.2s}.cw-suggestions button:hover{border-color:#becab0;transform:translateX(3px);background:#fff}.cw-suggestions button>span:first-child{font-size:22px;color:#8f9e7b}.cw-suggestions b{font-size:12px;font-weight:500;display:block;color:#515e48}.cw-suggestions small{font-size:10px;color:#949b8d;display:block;margin-top:5px}.cw-arrow{margin-left:auto;color:#919b87;font-size:17px}.cw-discovery-head{display:flex;align-items:center;justify-content:space-between;margin-top:34px;margin-bottom:15px}.cw-discovery-head h2{font-size:12px;font-weight:500;color:#5a6751}.cw-discovery-head>span{font-size:7px;letter-spacing:1.6px;color:#a2aa99}.cw-discovery{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:13px}.cw-discovery>button{min-width:0;border:0;padding:0;background:none;text-align:left;animation:cw-rise .6s both;animation-delay:var(--delay)}.cw-mini-poster{position:relative;aspect-ratio:2/3;border-radius:6px;overflow:hidden;background:linear-gradient(145deg,#b8bea6,#4c6056)}.cw-mini-poster img{width:100%;height:100%;object-fit:cover;transition:.3s}.cw-discovery>button:hover img{transform:scale(1.04)}.cw-mini-poster>span{position:absolute;bottom:8px;left:9px;color:#fff;font-size:10px;letter-spacing:1px;text-shadow:0 1px 7px #000}.cw-discovery b{display:block;font-size:10px;font-weight:500;margin-top:9px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;color:#505c49}.cw-discovery small{display:flex;justify-content:space-between;font-size:8px;color:#929b89;margin-top:5px}.cw-discovery small span{color:#a08c5e}.cw-context{width:255px;flex-shrink:0;padding:43px 25px 25px 22px;border-left:1px solid var(--line);min-height:calc(100vh - 76px);background:#f3f3ed;align-self:stretch}.cw-context-title{display:flex;gap:9px;align-items:center;color:#667356}.cw-context-title>span{font-size:25px}.cw-context-title b{font-size:12px;font-weight:500}.cw-context-caption{font-size:10px;color:#9aa18f;line-height:1.9;margin:15px 0 31px}.cw-context-block{border-top:1px solid #e3e6d9;padding:20px 0}.cw-context-block label{font-size:9px;color:#9aa28f;letter-spacing:1px}.cw-context-block>p{font-size:11px;color:#717d63;line-height:1.9;margin-top:10px;word-break:break-word}.cw-context-block small{display:block;color:#a5ad99;font-size:9px}.cw-context-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.cw-context-tags>span{font-size:9px;border:1px solid #d9dfcc;color:#7d8b6d;border-radius:4px;padding:5px 7px;background:#f9faf2}.cw-reset{font-size:10px!important;border:0;background:none;color:#909c7f;padding:0}.cw-note{display:flex;gap:9px;align-items:flex-start;margin-top:60px;color:#98a28c}.cw-note>span{font-size:23px}.cw-note p{font-size:10px;line-height:1.9}.cw-note small{font-size:9px;color:#a6af9b}.cw-composer-wrap{position:sticky;bottom:0;padding:25px 0 12px;background:linear-gradient(transparent,var(--bg) 20%);margin-top:16px;z-index:4}.cw-composer{background:#fffefa;border:1px solid #d9decf;border-radius:11px;padding:15px 17px 11px;box-shadow:0 4px 18px #42542e05}.cw-composer:focus-within{border-color:#9aab85;box-shadow:0 0 0 3px #9aab8510}.cw-composer textarea{display:block;width:100%;resize:none;background:none;border:none;outline:none;color:#4e5f42;font-size:12px;line-height:1.8}.cw-composer textarea::placeholder{color:#a3ac97}.cw-composer-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:8px}.cw-composer-bottom>span{font-size:9px;color:#a6af9a}.cw-composer-bottom button{width:30px;height:30px;background:#465c3c;color:#fff;border:0;border-radius:7px;font-size:22px}.cw-disclaimer{text-align:center;font-size:8px;letter-spacing:.2px;color:#a7ae9e;margin:10px 0 0}.cw-active-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:9px}.cw-active-chips button{border:1px solid #dce3d2;border-radius:20px;background:#eef2e5;color:#7d8c6c;font-size:9px;padding:4px 9px}.cw-active-chips span{padding-left:5px;color:#a3b28e}.cw-turn{padding:3px 0 25px;border-bottom:1px solid #e9eadd;margin-bottom:22px}.cw-user-message{display:flex;gap:13px;align-items:flex-start;margin-bottom:28px}.cw-user-message>span{flex-shrink:0;display:grid;place-items:center;width:27px;height:27px;border-radius:50%;background:#e4e9d8;font-size:10px;color:#859476}.cw-user-message p{padding:4px 0;color:#4c5b40;font-size:13px;line-height:1.8}.cw-assistant-head{display:flex;gap:9px;align-items:center}.cw-assistant-head .cw-symbol{font-size:27px}.cw-assistant-head b{font-size:13px;font-weight:600;color:#59634f}.cw-assistant-head small{font-size:8px;border:1px solid #dce2d0;padding:3px 5px;border-radius:3px;color:#9ba68b}.cw-reply{font-size:12px;line-height:1.9;color:#78816d;margin:13px 0 20px}.cw-film-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:17px 14px}.cw-film{background:#fefefa;border:1px solid #e3e7d8;border-radius:8px;overflow:hidden;min-width:0}.cw-film-poster{display:block;border:0;padding:0;width:100%;aspect-ratio:3/3.5;position:relative;background:linear-gradient(125deg,#607660,#abb59b);overflow:hidden}.cw-film-poster img{position:relative;z-index:1;width:100%;height:100%;object-fit:cover;object-position:center 25%;transition:.3s}.cw-film-poster:hover img{transform:scale(1.04)}.cw-film-number{position:absolute;left:9px;top:9px;z-index:2;font-size:10px;color:#fff;background:#172b23a0;border-radius:4px;padding:4px 6px}.cw-rating{position:absolute;right:8px;bottom:8px;z-index:2;background:#162820a6;color:#efde9c;border-radius:4px;padding:4px 6px;font-size:9px}.cw-poster-fallback{position:absolute;inset:0;display:grid;place-items:center;padding:15px;color:#f5f7e9;font-family:Georgia,serif;font-size:25px}.cw-film-info{padding:12px}.cw-film-title{font-size:12px!important;font-weight:600!important;color:#505e45;background:none;border:0;padding:0;text-align:left;line-height:1.5;min-height:18px}.cw-film-info>p:not(.cw-reason){font-size:9px;color:#9aa389;margin:6px 0 9px}.cw-film-info>p>span{margin:0 5px}.cw-genres{display:flex;gap:4px;flex-wrap:wrap}.cw-genres span{font-size:8px;color:#8c987a;background:#f0f3e9;padding:3px 5px;border-radius:3px}.cw-film-info .cw-reason{font-size:9px;color:#929c83;line-height:1.9;margin-top:10px;min-height:50px}.cw-film-actions{display:flex;border-top:1px solid #edf0e4;padding-top:9px;gap:9px}.cw-film-actions button{font-size:9px!important;padding:0;color:#a1ac91;border:0;background:none}.cw-film-actions button:last-child{margin-left:auto}.cw-film-actions button.chosen{color:#bd583c;font-weight:600}.cw-turn-footer{display:flex;justify-content:space-between;font-size:8px;color:#a8b098;margin-top:13px}.cw-thinking{display:flex;align-items:center;gap:4px;margin-top:16px;color:#9eaa8e}.cw-thinking>span{width:4px;height:4px;background:#9ba98a;border-radius:50%;animation:cw-pulse 1.2s infinite}.cw-thinking>span:nth-child(2){animation-delay:.2s}.cw-thinking>span:nth-child(3){animation-delay:.4s}.cw-thinking>p{font-size:10px;margin-left:8px}.cw-error{padding:12px;border:1px solid #ecd4c5;border-radius:7px;background:#fff5ec;color:#ad6e4b;font-size:11px;line-height:1.8}.cw-trace{margin-top:20px;padding-top:18px;border-top:1px solid #dfe6d2;color:#8b987a;font-size:9px;line-height:1.8}.cw-trace h3{font-size:10px}.cw-trace pre{overflow:auto;max-height:300px;font-size:8px;white-space:pre-wrap;word-break:break-all}.cw-modal-backdrop{position:fixed;inset:0;background:#18211970;backdrop-filter:blur(5px);z-index:60;display:grid;place-items:center;padding:25px}.cw-modal{position:relative;background:#fafbf4;border-radius:15px;max-width:680px;max-height:90vh;overflow:auto;padding:35px;color:#59664e;box-shadow:0 30px 80px #18211940}.cw-modal-close{position:absolute;right:15px;top:10px;border:0;background:none;font-size:25px;color:#8a987a}.cw-modal-top{display:flex;gap:25px;align-items:center}.cw-modal-top img{width:140px;aspect-ratio:2/3;object-fit:cover;border-radius:7px}.cw-modal-top small{font-size:8px;letter-spacing:2px;color:#a6ae99}.cw-modal-top h2{font:27px Georgia,serif;margin:13px 0}.cw-modal-top p{font-size:11px;margin-top:10px;color:#94a080}.cw-modal-top span{display:inline-block;margin-top:15px;font-size:11px;color:#a28b5b}.cw-modal>h3{margin-top:25px;font-size:12px}.cw-modal>p{font-size:12px;line-height:1.9;margin-top:10px;color:#859176}.cw-modal details{font-size:10px;margin-top:17px}.cw-modal pre{white-space:pre-wrap;word-break:break-word;font-size:10px;color:#94a080;margin-top:12px}.cw-detail-link{display:inline-block;margin-top:20px;text-decoration:none;color:#a86548;font-size:11px}@keyframes cw-rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}@keyframes cw-pulse{50%{opacity:.2}}@media(min-width:1600px){.cw-main{padding-left:8%;padding-right:8%}}@media(max-width:1180px){.cw-context{width:210px;padding-left:17px;padding-right:17px}.cw-sidebar{width:210px;padding-left:18px;padding-right:18px}.cw-workspace{margin-left:210px}.cw-main{padding-left:4%;padding-right:4%}.cw-film-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:900px){.cw-context{display:none}.cw-main{padding-left:6%;padding-right:6%}.cw-welcome h1{font-size:55px}.cw-topbar{padding:0 25px}.cw-topbar .cw-text-button{display:none}}@media(max-width:640px){.cw-sidebar{display:none}.cw-workspace{margin-left:0}.cw-topbar{height:56px;padding:0 20px}.cw-topbar>span{font-size:10px}.cw-main{padding:28px 20px 0}.cw-welcome h1{font-size:46px}.cw-eyebrow{font-size:7px;letter-spacing:1.5px}.cw-discovery{gap:8px}.cw-discovery>button:nth-child(5){display:none}.cw-discovery{grid-template-columns:repeat(4,minmax(0,1fr))}.cw-suggestions button{padding:12px}.cw-suggestions small{line-height:1.7}.cw-film-grid{gap:12px 9px}.cw-film-info{padding:10px}.cw-composer-wrap{padding-bottom:10px}.cw-modal{padding:25px}.cw-modal-top{gap:15px}.cw-modal-top img{width:100px}.cw-modal-top h2{font-size:22px}.cw-turn-footer{gap:8px;line-height:1.8}}
.cw-context{position:sticky;top:76px;align-self:flex-start;height:calc(100vh - 76px);overflow-y:auto}
</style>
