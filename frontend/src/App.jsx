import { useEffect, useState, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  fetchState,
  addKnight,
  createDragonSpot,
  createTarget,
  createTrebuchet,
  deleteKnight,
  deleteTarget,
  deleteDragonSpot,
  resetSession,
  setGameActive,
  transcribeAudio,
  chat,
} from './api'

const GRID_W = 55
const GRID_H = 30
const POLL_MS = 500

function nearestLocation(locations, gx, gy) {
  if (!locations?.length) return null
  let best = locations[0]
  let bestD = Infinity
  for (const loc of locations) {
    const d = (loc.x - gx) ** 2 + (loc.y - gy) ** 2
    if (d < bestD) {
      bestD = d
      best = loc
    }
  }
  return best
}

function MapView({ state, onMapClick, onEntityClick, fireBreathAtLocation }) {
  if (!state) return <div className="p-4">Loading…</div>

  const { grid, locations, knights, dragon_spots, targets, trebuchets = [] } = state
  const w = grid?.width ?? GRID_W
  const h = grid?.height ?? GRID_H
  const fireBreathLoc = fireBreathAtLocation && locations?.find((l) => l.name === fireBreathAtLocation)

  const handleMapClick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const gx = (x / rect.width) * w
    const gy = (y / rect.height) * h
    const loc = nearestLocation(locations, gx, gy)
    onMapClick(loc, { x: e.clientX, y: e.clientY })
  }

  const blockPctX = (v) => (v / w) * 100
  const blockPctY = (v) => (v / h) * 100

  return (
    <div className="relative w-full max-w-4xl aspect-[55/30] bg-stone-800 rounded-lg overflow-hidden">
      {/* Background map image */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: 'url(/assets/map.png)' }}
      />
      {/* Semi-transparent grid */}
      <div
        className="absolute inset-0 opacity-30 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255,255,255,0.15) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255,255,255,0.15) 1px, transparent 1px)
          `,
          backgroundSize: `${100 / w}% ${100 / h}%`,
        }}
      />
      {/* Clickable overlay for context menu */}
      <div
        className="absolute inset-0 cursor-crosshair"
        onClick={handleMapClick}
      />

      {/* Knights */}
      {knights?.map((k) => (
        <KnightMarker
          key={k.id}
          knight={k}
          blockPctX={blockPctX}
          blockPctY={blockPctY}
          onClick={(e) => {
            e.stopPropagation()
            onEntityClick('knight', k, { x: e.clientX, y: e.clientY })
          }}
        />
      ))}

      {/* Dragon spots (optional: show as icon; or only in list) */}
      {dragon_spots?.map((d) => (
        <DragonMarker
          key={d.id}
          dragon={d}
          blockPctX={blockPctX}
          blockPctY={blockPctY}
          onClick={(e) => {
            e.stopPropagation()
            onEntityClick('dragon', d, { x: e.clientX, y: e.clientY })
          }}
        />
      ))}

      {/* Targets */}
      {targets?.map((t) => (
        <TargetMarker
          key={t.id}
          target={t}
          blockPctX={blockPctX}
          blockPctY={blockPctY}
          onClick={(e) => {
            e.stopPropagation()
            onEntityClick('target', t, { x: e.clientX, y: e.clientY })
          }}
        />
      ))}

      {/* Trebuchets */}
      {trebuchets?.map((tr) => (
        <TrebuchetMarker
          key={tr.id}
          trebuchet={tr}
          blockPctX={blockPctX}
          blockPctY={blockPctY}
        />
      ))}

      {/* Fire-breath overlay when knight is killed */}
      {fireBreathLoc && (
        <motion.div
          initial={{ opacity: 1, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1.2 }}
          exit={{ opacity: 0 }}
          className="absolute w-16 h-16 -ml-8 -mt-8 z-20 pointer-events-none"
          style={{
            left: `${blockPctX(fireBreathLoc.x)}%`,
            top: `${blockPctY(fireBreathLoc.y)}%`,
          }}
        >
          <img src="/assets/fire-breath.gif" alt="" className="w-full h-full object-contain" />
        </motion.div>
      )}
    </div>
  )
}

function KnightMarker({ knight, blockPctX, blockPctY, onClick }) {
  const neutralized = false // knights don't have status
  return (
    <motion.div
      layout
      initial={false}
      animate={{
        left: `${blockPctX(knight.x)}%`,
        top: `${blockPctY(knight.y)}%`,
      }}
      transition={{ duration: 2, ease: 'easeInOut' }}
      className="absolute w-8 h-8 -ml-4 -mt-4 cursor-pointer z-10 select-none"
      style={{ pointerEvents: 'auto' }}
      onClick={onClick}
    >
      <img
        src="/assets/knight.png"
        alt="Knight"
        className={`w-full h-full object-contain ${neutralized ? 'opacity-50 grayscale' : ''}`}
        draggable={false}
      />
    </motion.div>
  )
}

function DragonMarker({ dragon, blockPctX, blockPctY, onClick }) {
  const neutralized = dragon.status === 'neutralized'
  return (
    <motion.div
      layout
      initial={false}
      animate={{
        left: `${blockPctX(dragon.x)}%`,
        top: `${blockPctY(dragon.y)}%`,
      }}
      className="absolute w-8 h-8 -ml-4 -mt-4 cursor-pointer z-10 select-none"
      style={{ pointerEvents: 'auto' }}
      onClick={onClick}
    >
      <img
        src="/assets/dragon.png"
        alt="Dragon"
        className={`w-full h-full object-contain ${neutralized ? 'opacity-50 grayscale' : ''}`}
        draggable={false}
      />
    </motion.div>
  )
}

function TargetMarker({ target, blockPctX, blockPctY, onClick }) {
  const neutralized = target.status === 'neutralized'
  const [showHit, setShowHit] = useState(false)
  const prevStatus = useRef(target.status)

  useEffect(() => {
    if (target.status === 'neutralized' && prevStatus.current !== 'neutralized') {
      prevStatus.current = 'neutralized'
      setShowHit(true)
      const t = setTimeout(() => setShowHit(false), 800)
      return () => clearTimeout(t)
    }
  }, [target.status])

  return (
    <motion.div
      layout
      initial={false}
      animate={{
        left: `${blockPctX(target.x)}%`,
        top: `${blockPctY(target.y)}%`,
      }}
      className="absolute w-8 h-8 -ml-4 -mt-4 cursor-pointer z-10 select-none"
      style={{ pointerEvents: 'auto' }}
      onClick={onClick}
    >
      <img
        src="/assets/target.png"
        alt="Target"
        className={`w-full h-full object-contain ${neutralized ? 'opacity-50 grayscale' : ''}`}
        draggable={false}
      />
      <AnimatePresence>
        {showHit && (
          <motion.div
            initial={{ opacity: 1, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1.5 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
          >
            <img src="/assets/hitspark.gif" alt="" className="w-12 h-12 object-contain" />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function TrebuchetMarker({ trebuchet, blockPctX, blockPctY }) {
  return (
    <motion.div
      layout
      initial={false}
      animate={{
        left: `${blockPctX(trebuchet.x)}%`,
        top: `${blockPctY(trebuchet.y)}%`,
      }}
      className="absolute w-8 h-8 -ml-4 -mt-4 z-10 select-none pointer-events-none"
      title={`Trebuchet at ${trebuchet.location}`}
    >
      <img
        src="/assets/trebuchet.png"
        alt="Trebuchet"
        className="w-full h-full object-contain"
        draggable={false}
      />
    </motion.div>
  )
}

function ContextMenu({ x, y, items, onClose }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="fixed z-50 py-1 min-w-[180px] bg-stone-800 border border-stone-600 rounded-lg shadow-xl"
        style={{ left: x, top: y }}
      >
        {items.map(({ label, action }) => (
          <button
            key={label}
            type="button"
            className="w-full px-4 py-2 text-left text-sm text-stone-200 hover:bg-stone-700"
            onClick={() => {
              action()
              onClose()
            }}
          >
            {label}
          </button>
        ))}
      </motion.div>
    </>
  )
}

function TopBar({ time, onReset, gameActive, onGameActiveChange, trebuchetCooldown, musicMuted, onMusicMutedChange, onStartMusic }) {
  return (
    <header className="flex items-center justify-between gap-4 py-3 px-4 bg-stone-800/80 border-b border-stone-600 rounded-t-lg flex-wrap">
      <h1 className="text-lg font-semibold text-stone-100 truncate">{"Knights & Nodes - A Voice Controlled C&C Demo"}</h1>
      <div className="flex items-center gap-3">
        {trebuchetCooldown > 0 && (
          <span className="flex items-center gap-1.5 px-2 py-1 rounded bg-amber-900/80 text-amber-200 text-sm" title="Trebuchet cooldown">
            <span className="text-base" aria-hidden>⏱</span>
            <span className="tabular-nums font-medium">{trebuchetCooldown}</span>
          </span>
        )}
        <button
          type="button"
          onClick={() => {
            if (musicMuted && gameActive) onStartMusic?.(true)
            onMusicMutedChange(!musicMuted)
          }}
          className={`px-2.5 py-1.5 text-sm font-medium rounded ${musicMuted ? 'bg-stone-700 text-stone-500' : 'bg-stone-600 text-stone-200 hover:bg-stone-500'}`}
          title={musicMuted ? 'Unmute music' : 'Mute music'}
          aria-label={musicMuted ? 'Unmute music' : 'Mute music'}
        >
          <span className="text-lg" aria-hidden>{musicMuted ? '🔇' : '🎵'}</span>
        </button>
        <button
          type="button"
          onClick={() => {
            if (!gameActive) onStartMusic?.()
            onGameActiveChange(!gameActive)
          }}
          className={`px-3 py-1.5 text-sm font-medium rounded ${gameActive ? 'bg-emerald-600 text-white hover:bg-emerald-500' : 'bg-stone-600 text-stone-200 hover:bg-stone-500'}`}
        >
          {gameActive ? 'Simulation ON' : 'Start Game'}
        </button>
        <span className="text-sm text-stone-400 tabular-nums">{time}</span>
        <button
          type="button"
          onClick={onReset}
          className="px-3 py-1.5 text-sm font-medium rounded bg-stone-600 text-stone-200 hover:bg-stone-500"
        >
          Reset session
        </button>
      </div>
    </header>
  )
}

const TABLE_TABS = ['Knights', 'Dragon spots', 'Targets']

function StateTables({ state, activeTab, onTabChange }) {
  if (!state) return null
  const { knights = [], dragon_spots = [], targets = [] } = state
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex gap-1 border-b border-stone-600 mb-2">
        {TABLE_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => onTabChange(tab)}
            className={`px-3 py-2 text-sm font-medium rounded-t ${
              activeTab === tab ? 'bg-stone-600 text-stone-100' : 'text-stone-400 hover:text-stone-200'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto rounded border border-stone-600">
        {activeTab === 'Knights' && (
          <table className="w-full text-left text-sm">
            <thead className="bg-stone-700 text-stone-300 sticky top-0">
              <tr>
                <th className="p-2">Id</th>
                <th className="p-2">Name</th>
                <th className="p-2">Location</th>
              </tr>
            </thead>
            <tbody>
              {knights.length === 0 ? (
                <tr><td colSpan={3} className="p-2 text-stone-500">(none)</td></tr>
              ) : (
                knights.map((k) => (
                  <tr key={k.id} className="border-t border-stone-600">
                    <td className="p-2 font-mono text-xs">{k.id}</td>
                    <td className="p-2">{k.name}</td>
                    <td className="p-2">{k.location}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
        {activeTab === 'Dragon spots' && (
          <table className="w-full text-left text-sm">
            <thead className="bg-stone-700 text-stone-300 sticky top-0">
              <tr>
                <th className="p-2">Id</th>
                <th className="p-2">Location</th>
                <th className="p-2">Type</th>
                <th className="p-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {dragon_spots.length === 0 ? (
                <tr><td colSpan={4} className="p-2 text-stone-500">(none)</td></tr>
              ) : (
                dragon_spots.map((d) => (
                  <tr key={d.id} className="border-t border-stone-600">
                    <td className="p-2 font-mono text-xs">{d.id}</td>
                    <td className="p-2">{d.location}</td>
                    <td className="p-2">{d.type}</td>
                    <td className="p-2">{d.status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
        {activeTab === 'Targets' && (
          <table className="w-full text-left text-sm">
            <thead className="bg-stone-700 text-stone-300 sticky top-0">
              <tr>
                <th className="p-2">Id</th>
                <th className="p-2">Location</th>
                <th className="p-2">Linked dragon</th>
                <th className="p-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {targets.length === 0 ? (
                <tr><td colSpan={4} className="p-2 text-stone-500">(none)</td></tr>
              ) : (
                targets.map((t) => (
                  <tr key={t.id} className="border-t border-stone-600">
                    <td className="p-2 font-mono text-xs">{t.id}</td>
                    <td className="p-2">{t.location}</td>
                    <td className="p-2 font-mono text-xs">{t.linked_dragon_spot_id || '—'}</td>
                    <td className="p-2">{t.status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function TurnLog({ turnLogs = [] }) {
  const endRef = useRef(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turnLogs.length])
  return (
    <div className="flex flex-col gap-1 min-h-0">
      <label className="text-xs font-medium text-stone-400">Turn log</label>
      <div className="flex-1 min-h-[80px] max-h-32 overflow-y-auto rounded border border-stone-600 bg-stone-900 px-2 py-1.5 text-xs text-stone-300 font-mono">
        {turnLogs.length === 0 ? (
          <span className="text-stone-500">(no events yet)</span>
        ) : (
          turnLogs.map((line, i) => <div key={i}>{line}</div>)
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}

function RightPanel({
  transcription,
  llmResult,
  isRecording,
  onPtTDown,
  onPtTUp,
  state,
  tableTab,
  onTableTabChange,
  turnLogs,
}) {
  return (
    <aside className="flex flex-col w-full max-w-md bg-stone-800/90 border border-stone-600 rounded-lg overflow-hidden">
      <div className="p-3 border-b border-stone-600">
        <p className="text-xs text-stone-400 mb-2">Hold to speak, release to transcribe and send to LLM.</p>
        <button
          type="button"
          onPointerDown={onPtTDown}
          onPointerUp={onPtTUp}
          onPointerLeave={onPtTUp}
          className={`w-full py-3 rounded-lg font-semibold select-none touch-none ${
            isRecording ? 'bg-red-600 text-white' : 'bg-emerald-600 text-white hover:bg-emerald-500'
          }`}
        >
          {isRecording ? 'Recording…' : 'Hold to talk'}
        </button>
      </div>
      <div className="p-3 border-b border-stone-600 flex flex-col gap-2">
        <TurnLog turnLogs={turnLogs} />
      </div>
      <div className="p-3 border-b border-stone-600 flex flex-col gap-2">
        <label className="text-xs font-medium text-stone-400">Transcription</label>
        <textarea
          readOnly
          value={transcription}
          placeholder="(transcription will appear here)"
          className="w-full h-20 px-3 py-2 text-sm bg-stone-900 border border-stone-600 rounded resize-none text-stone-200 placeholder-stone-500"
          rows={3}
        />
      </div>
      <div className="p-3 border-b border-stone-600 flex flex-col gap-2">
        <label className="text-xs font-medium text-stone-400">LLM result</label>
        <textarea
          readOnly
          value={llmResult}
          placeholder="(LLM response and tool results)"
          className="w-full h-24 px-3 py-2 text-sm bg-stone-900 border border-stone-600 rounded resize-none text-stone-200 placeholder-stone-500"
          rows={4}
        />
      </div>
      <div className="flex-1 min-h-0 p-3 flex flex-col">
        <label className="text-xs font-medium text-stone-400 mb-2">State</label>
        <StateTables state={state} activeTab={tableTab} onTabChange={onTableTabChange} />
      </div>
    </aside>
  )
}

const MUSIC_TRACKS = ['/assets/You_Meet_in_a_Tavern.mp3', '/assets/Quiet_Hearth.mp3']

export default function App() {
  const [state, setState] = useState(null)
  const [menu, setMenu] = useState(null)
  const [time, setTime] = useState(() => new Date().toLocaleTimeString())
  const [transcription, setTranscription] = useState('')
  const [llmResult, setLlmResult] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [tableTab, setTableTab] = useState('Knights')
  const [musicMuted, setMusicMuted] = useState(false)
  const [fireBreathAtLocation, setFireBreathAtLocation] = useState(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const musicRef = useRef(null)
  const musicIndexRef = useRef(0)
  const gameActiveRef = useRef(false)
  const musicMutedRef = useRef(false)
  const sfxRef = useRef(null)

  const loadState = useCallback(async () => {
    try {
      const data = await fetchState()
      setState(data)
    } catch (e) {
      console.error(e)
    }
  }, [])

  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toLocaleTimeString()), 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    loadState()
    const id = setInterval(loadState, POLL_MS)
    return () => clearInterval(id)
  }, [loadState])

  // One-shot effect sounds and fire-breath overlay (no cleanup so timeout always runs and hides gif)
  useEffect(() => {
    if (!state?.effect_knight_killed_at) return
    setFireBreathAtLocation(state.effect_knight_killed_at)
    setTimeout(() => setFireBreathAtLocation(null), 2200)
    if (!sfxRef.current) sfxRef.current = new Audio()
    sfxRef.current.src = '/assets/dragon-slays-knight.mp3'
    sfxRef.current.play().catch(() => {})
  }, [state?.effect_knight_killed_at])
  useEffect(() => {
    if (!state?.effect_dragon_killed_by_knight_at) return
    if (!sfxRef.current) sfxRef.current = new Audio()
    sfxRef.current.src = '/assets/sword_slice.mp3'
    sfxRef.current.play().catch(() => {})
  }, [state?.effect_dragon_killed_by_knight_at])
  useEffect(() => {
    if (!state?.effect_dragon_killed_by_artillery_at) return
    if (!sfxRef.current) sfxRef.current = new Audio()
    sfxRef.current.src = '/assets/mortar_hit.mp3'
    sfxRef.current.play().catch(() => {})
  }, [state?.effect_dragon_killed_by_artillery_at])

  // Background music: start only from user gesture (click Start Game or Unmute); useEffect only stops when game off or muted
  gameActiveRef.current = state?.game_active ?? false
  musicMutedRef.current = musicMuted

  const startMusic = useCallback((forceStart = false) => {
    if (!forceStart && musicMutedRef.current) return
    if (forceStart) musicMutedRef.current = false
    gameActiveRef.current = true
    if (!musicRef.current) musicRef.current = new Audio()
    const audio = musicRef.current
    const playNext = () => {
      if (!gameActiveRef.current || musicMutedRef.current) {
        audio.pause()
        return
      }
      const idx = musicIndexRef.current % MUSIC_TRACKS.length
      audio.src = MUSIC_TRACKS[idx]
      musicIndexRef.current += 1
      audio.onended = playNext
      audio.play().catch((e) => {
        console.warn('Music play failed:', e?.name || e)
      })
    }
    musicIndexRef.current = 0
    playNext()
  }, [])

  useEffect(() => {
    if (!musicRef.current) musicRef.current = new Audio()
    const audio = musicRef.current
    if (!gameActiveRef.current || musicMutedRef.current) {
      audio.pause()
      audio.currentTime = 0
      audio.onended = null
    }
  }, [state?.game_active, musicMuted])

  const handleReset = useCallback(async () => {
    try {
      await resetSession()
      loadState()
      setTranscription('')
      setLlmResult('')
    } catch (e) {
      console.error(e)
    }
  }, [loadState])

  const handleGameActiveChange = useCallback(async (active) => {
    try {
      await setGameActive(active)
      loadState()
    } catch (e) {
      console.error(e)
    }
  }, [loadState])

  const handleMusicMutedChange = useCallback((muted) => {
    setMusicMuted(muted)
    if (!muted && (state?.game_active)) startMusic()
  }, [state?.game_active, startMusic])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setTranscription('Transcribing…')
        setLlmResult('')
        try {
          const text = await transcribeAudio(blob)
          setTranscription(text || '(empty)')
          if (!text) {
            setLlmResult('(no speech to send)')
            return
          }
          setLlmResult('Sending to LLM…')
          const out = await chat(text)
          const parts = [out.content].filter(Boolean)
          if (out.tool_results?.length) {
            out.tool_results.forEach((r) => parts.push(`Tool: ${r.tool}(${JSON.stringify(r.arguments)})\nResult: ${r.result}`))
          }
          if (out.error) parts.push(`Error: ${out.error}`)
          setLlmResult(parts.join('\n\n') || '(no response)')
          loadState()
        } catch (err) {
          setTranscription((t) => (t === 'Transcribing…' ? '' : t))
          setLlmResult(err?.message || 'Error')
        }
      }
      recorder.start()
      recorderRef.current = recorder
      setIsRecording(true)
    } catch (err) {
      setLlmResult(err?.message || 'Microphone error')
    }
  }, [loadState])

  const stopRecording = useCallback(() => {
    if (!recorderRef.current || recorderRef.current.state !== 'recording') return
    recorderRef.current.stop()
    recorderRef.current = null
    setIsRecording(false)
  }, [])

  const handleMapClick = (location, screenPos) => {
    if (!location) return
    const trebuchetAvailable = state?.trebuchet_available !== false
    const items = [
      {
        label: `Spawn Knight at ${location.name}`,
        action: () => addKnight(location.name).then(loadState),
      },
      {
        label: `Spawn Dragon at ${location.name}`,
        action: () => createDragonSpot(location.name).then(loadState),
      },
      {
        label: `Spawn Target at ${location.name}`,
        action: () => createTarget(location.name).then(loadState),
      },
    ]
    if (trebuchetAvailable) {
      items.push({
        label: `Build Trebuchet at ${location.name}`,
        action: () => createTrebuchet(location.name).then(loadState),
      })
    }
    setMenu({
      x: screenPos.x,
      y: screenPos.y,
      items,
    })
  }

  const handleEntityClick = (kind, entity, screenPos) => {
    if (kind === 'knight') {
      setMenu({
        x: screenPos.x,
        y: screenPos.y,
        items: [
          { label: 'Delete', action: () => deleteKnight(entity.id).then(loadState) },
        ],
      })
    } else if (kind === 'target') {
      setMenu({
        x: screenPos.x,
        y: screenPos.y,
        items: [
          { label: 'Delete', action: () => deleteTarget(entity.id).then(loadState) },
        ],
      })
    } else if (kind === 'dragon') {
      setMenu({
        x: screenPos.x,
        y: screenPos.y,
        items: [
          { label: 'Delete', action: () => deleteDragonSpot(entity.id).then(loadState) },
        ],
      })
    }
  }

  const gameActive = state?.game_active ?? false
  const turnLogs = state?.turn_logs ?? []
  const trebuchetCooldown = state?.trebuchet_cooldown ?? 0
  const defeat = state?.knights?.length === 0

  return (
    <div className="min-h-screen bg-stone-900 text-stone-100 flex flex-col">
      <TopBar
        time={time}
        onReset={handleReset}
        gameActive={gameActive}
        onGameActiveChange={handleGameActiveChange}
        onStartMusic={startMusic}
        trebuchetCooldown={trebuchetCooldown}
        musicMuted={musicMuted}
        onMusicMutedChange={handleMusicMutedChange}
      />
      <div className="flex-1 flex gap-4 p-4 min-h-0 overflow-hidden">
        <div className="flex-1 min-w-0 flex flex-col">
          <MapView
            state={state}
            onMapClick={handleMapClick}
            onEntityClick={handleEntityClick}
            fireBreathAtLocation={fireBreathAtLocation}
          />
        </div>
        <div className="flex-shrink-0 flex flex-col min-h-0 w-80">
          <RightPanel
            transcription={transcription}
            llmResult={llmResult}
            isRecording={isRecording}
            onPtTDown={startRecording}
            onPtTUp={stopRecording}
            state={state}
            tableTab={tableTab}
            onTableTabChange={setTableTab}
            turnLogs={turnLogs}
          />
        </div>
      </div>
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menu.items}
          onClose={() => setMenu(null)}
        />
      )}
      <AnimatePresence>
        {defeat && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-stone-800 border-2 border-red-600 rounded-xl p-8 text-center shadow-2xl"
            >
              <h2 className="text-3xl font-bold text-red-500 mb-2">DEFEAT</h2>
              <p className="text-stone-300 mb-4">All knights have fallen.</p>
              <button
                type="button"
                onClick={() => handleReset().then(() => loadState())}
                className="px-4 py-2 bg-stone-600 text-stone-100 rounded hover:bg-stone-500"
              >
                Reset & try again
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
