import { useEffect, useState, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  fetchState,
  addKnight,
  createTarget,
  deleteKnight,
  deleteTarget,
  deleteDragonSpot,
  resetSession,
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

function MapView({ state, onMapClick, onEntityClick }) {
  if (!state) return <div className="p-4">Loading…</div>

  const { grid, locations, knights, dragon_spots, targets } = state
  const w = grid?.width ?? GRID_W
  const h = grid?.height ?? GRID_H

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
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
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

function TopBar({ time, onReset }) {
  return (
    <header className="flex items-center justify-between gap-4 py-3 px-4 bg-stone-800/80 border-b border-stone-600 rounded-t-lg">
      <h1 className="text-lg font-semibold text-stone-100 truncate">{"Knights & Nodes - A Voice Controlled C&C Demo"}</h1>
      <span className="text-sm text-stone-400 tabular-nums">{time}</span>
      <button
        type="button"
        onClick={onReset}
        className="px-3 py-1.5 text-sm font-medium rounded bg-stone-600 text-stone-200 hover:bg-stone-500"
      >
        Reset session
      </button>
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

function RightPanel({
  transcription,
  llmResult,
  isRecording,
  onPtTDown,
  onPtTUp,
  state,
  tableTab,
  onTableTabChange,
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

export default function App() {
  const [state, setState] = useState(null)
  const [menu, setMenu] = useState(null)
  const [time, setTime] = useState(() => new Date().toLocaleTimeString())
  const [transcription, setTranscription] = useState('')
  const [llmResult, setLlmResult] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [tableTab, setTableTab] = useState('Knights')
  const recorderRef = useRef(null)
  const chunksRef = useRef([])

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
    setMenu({
      x: screenPos.x,
      y: screenPos.y,
      items: [
        {
          label: `Spawn Knight at ${location.name}`,
          action: () => addKnight(location.name).then(loadState),
        },
        {
          label: `Spawn Target at ${location.name}`,
          action: () => createTarget(location.name).then(loadState),
        },
      ],
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

  return (
    <div className="min-h-screen bg-stone-900 text-stone-100 flex flex-col">
      <TopBar time={time} onReset={handleReset} />
      <div className="flex-1 flex gap-4 p-4 min-h-0 overflow-hidden">
        <div className="flex-1 min-w-0 flex flex-col">
          <MapView
            state={state}
            onMapClick={handleMapClick}
            onEntityClick={handleEntityClick}
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
    </div>
  )
}
