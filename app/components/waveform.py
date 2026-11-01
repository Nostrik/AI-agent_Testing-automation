"""Звуковая диаграмма звонка (wavesurfer.js): волна по каналам, реплики агента и клиента цветными
областями, долгие паузы перед ответом агента красным. Клик по реплике или паузе — воспроизведение с этого места.

Аудио встраивается в страницу как data-URL, библиотека грузится браузером с unpkg.com
(нужен интернет на компьютере, где открыт тестер; на сервер ничего не ставится).
"""
import base64
import json
import mimetypes

import streamlit as st
import streamlit.components.v1 as components

WAVESURFER = "https://unpkg.com/wavesurfer.js@7.8.6/dist"

TEMPLATE = r"""
<style>
  :root { --fg: __FG__; --muted: __MUTED__; --line: __LINE__; }
  body { margin: 0; font: 13px/1.4 "Source Sans Pro", system-ui, sans-serif; color: var(--fg); background: transparent; }
  .bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 6px; }
  button, select { font: inherit; color: var(--fg); background: transparent; border: 1px solid var(--line);
                   border-radius: 6px; padding: 3px 10px; cursor: pointer; }
  #play { min-width: 44px; }
  #time { font-variant-numeric: tabular-nums; color: var(--muted); min-width: 110px; }
  .legend { display: flex; gap: 10px; color: var(--muted); margin-left: auto; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
  .ch { color: var(--muted); font-size: 11px; margin: 2px 0; }
  #chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  #chips button { border-color: __SLOW_LINE__; font-size: 12px; padding: 2px 8px; }
  #msg { color: var(--muted); margin-top: 6px; }
</style>
<div class="bar">
  <button id="play" title="Пробел — пауза">▶</button>
  <span id="time">0.0 / 0.0 с</span>
  <label>Скорость <select id="rate">
    <option>0.75</option><option selected>1</option><option>1.25</option><option>1.5</option><option>2</option>
  </select></label>
  <label>Масштаб <input id="zoom" type="range" min="0" max="300" step="10" value="0"></label>
  <span class="legend">
    <span><i style="background:__AGENT_SOLID__"></i>агент</span>
    <span><i style="background:__CLIENT_SOLID__"></i>клиент</span>
    <span><i style="background:__SLOW_SOLID__"></i>пауза дольше __SLOW__ с</span>
  </span>
</div>
<div class="ch" id="chlabel"></div>
<div id="wave"></div>
<div id="tl"></div>
<div id="chips"></div>
<div id="msg">Загружаю звуковую диаграмму…</div>
<script type="module">
import WaveSurfer from '__WS__/wavesurfer.esm.js'
import RegionsPlugin from '__WS__/plugins/regions.esm.js'
import TimelinePlugin from '__WS__/plugins/timeline.esm.js'

const D = __DATA__
const msg = document.getElementById('msg')
const fmt = s => (Math.round(s * 10) / 10).toFixed(1)
const regions = RegionsPlugin.create()
const ch = (color, progress) => ({ waveColor: color, progressColor: progress, height: 64 })
const ws = WaveSurfer.create({
  container: '#wave', url: D.url, normalize: true, cursorColor: D.fg, cursorWidth: 2,
  waveColor: D.agentSolid, progressColor: D.progress, height: 110,
  ...(D.stereo ? { splitChannels: D.agentFirst
      ? [ch(D.agentSolid, D.progress), ch(D.clientSolid, D.progress)]
      : [ch(D.clientSolid, D.progress), ch(D.agentSolid, D.progress)] } : {}),
  plugins: [regions, TimelinePlugin.create({ container: '#tl', style: { color: D.muted, fontSize: '11px' } })],
})
if (D.stereo) document.getElementById('chlabel').textContent =
  D.agentFirst ? 'Верхний канал — агент, нижний — клиент' : 'Верхний канал — клиент, нижний — агент'

const label = (text, title) => {
  const el = document.createElement('div')
  el.textContent = text
  el.title = title
  el.style.cssText = `font-size:11px;color:${D.fg};padding:2px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;`
  return el
}

ws.on('decode', () => {
  msg.textContent = 'Клик по реплике или паузе — воспроизведение с этого места.'
  for (const t of D.turns) {
    const who = t.role === 'agent' ? 'Агент' : 'Клиент'
    regions.addRegion({
      start: t.start, end: Math.max(t.end, t.start + 0.05), drag: false, resize: false,
      color: t.backchannel ? D.back : (t.role === 'agent' ? D.agent : D.client),
      content: t.backchannel ? undefined : label(t.text, `${who} · ${fmt(t.start)} с\n${t.text}`),
    })
  }
  const chips = document.getElementById('chips')
  for (const g of D.gaps) {
    regions.addRegion({ start: g.start, end: g.end, drag: false, resize: false, color: D.slow,
                        content: label(`${fmt(g.gap)} с`, `Пауза перед ответом агента: ${fmt(g.gap)} с`) })
    const b = document.createElement('button')
    b.textContent = `⏸ ${fmt(g.gap)} с · на ${fmt(g.start)} с`
    b.title = 'Прослушать: за 1.5 с до паузы и ответ агента'
    b.onclick = () => { ws.setTime(Math.max(0, g.start - 1.5)); ws.play() }
    chips.appendChild(b)
  }
})
regions.on('region-clicked', (r, e) => { e.stopPropagation(); r.play() })

const play = document.getElementById('play'), time = document.getElementById('time')
play.onclick = () => ws.playPause()
ws.on('play', () => { play.textContent = '❚❚' })
ws.on('pause', () => { play.textContent = '▶' })
ws.on('timeupdate', t => { time.textContent = `${fmt(t)} / ${fmt(ws.getDuration())} с` })
ws.on('ready', d => { time.textContent = `0.0 / ${fmt(d)} с` })
ws.on('error', e => { msg.textContent = 'Не удалось показать диаграмму: ' + e })
document.getElementById('rate').onchange = e => ws.setPlaybackRate(Number(e.target.value), true)
document.getElementById('zoom').oninput = e => ws.zoom(Number(e.target.value))
document.addEventListener('keydown', e => { if (e.code === 'Space') { e.preventDefault(); ws.playPause() } })
window.__wsLoaded = true
</script>
<script>
setTimeout(() => { if (!window.__wsLoaded) document.getElementById('msg').textContent =
  'Звуковая диаграмма не загрузилась: нет доступа к unpkg.com. Плеер ниже работает и без неё.' }, 8000)
</script>
"""


def _dark() -> bool:
    try:
        return st.context.theme.type != "light"
    except Exception:  # noqa: BLE001 — старые версии Streamlit
        return (st.get_option("theme.base") or "dark") != "light"


def waveform(data: bytes, name: str, turns: list[dict], slow_s: float, stereo: bool, agent_channel: str = "left"):
    """Рисует звуковую диаграмму под заголовком файла на странице «Анализ аудио»."""
    mime = mimetypes.guess_type(name)[0] or "audio/mpeg"
    dark = _dark()
    agent_solid, client_solid, slow_solid = "#4F8BF9", "#2EBD85", "#EF4444"
    gaps = [{"start": round(t["start"] - t["gap_s"], 3), "end": t["start"], "gap": t["gap_s"]}
            for t in turns if t["role"] == "agent" and t.get("after") == "client" and not t.get("backchannel")
            and t.get("gap_s") is not None and t["gap_s"] > slow_s]
    payload = {
        "url": f"data:{mime};base64," + base64.b64encode(data).decode(),
        "stereo": bool(stereo), "agentFirst": agent_channel == "left",
        "turns": [{"role": t["role"], "start": t["start"], "end": t["end"], "text": t.get("text") or "",
                   "backchannel": bool(t.get("backchannel"))} for t in turns],
        "gaps": sorted(gaps, key=lambda g: g["start"]),
        "agent": "rgba(79,139,249,.22)", "client": "rgba(46,189,133,.22)", "back": "rgba(150,150,150,.18)",
        "slow": "rgba(239,68,68,.38)", "agentSolid": agent_solid, "clientSolid": client_solid,
        "progress": "#A3A3A3" if dark else "#525252",
        "fg": "#E6E6E6" if dark else "#1F2328", "muted": "#9AA0A6" if dark else "#57606A",
    }
    page = (TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__WS__", WAVESURFER).replace("__SLOW__", f"{slow_s:g}")
            .replace("__AGENT_SOLID__", agent_solid).replace("__CLIENT_SOLID__", client_solid)
            .replace("__SLOW_SOLID__", slow_solid).replace("__SLOW_LINE__", "rgba(239,68,68,.6)")
            .replace("__FG__", payload["fg"]).replace("__MUTED__", payload["muted"])
            .replace("__LINE__", "#3D444D" if dark else "#D0D7DE"))
    height = (2 * 64 if stereo else 110) + 130 + (34 if gaps else 0)
    components.html(page, height=height)
