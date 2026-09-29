import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowRight, Compass, MapPin, Menu, Plus, Send, X } from 'lucide-react'
import PlanTable from './PlanTable'

const prompts = [
  { label: 'Five days in Bhopal', text: 'Plan a 5-day Bhopal, India trip with heritage sights and a relaxed pace.' },
  { label: 'A week in Lisbon', text: 'Plan 7 days in Lisbon, Portugal for two people who enjoy food and architecture.' },
  { label: 'Weather for Tokyo', text: 'What is the current weather and next three days of forecast in Tokyo, Japan?' },
  { label: 'Convert INR to EUR', text: 'Convert 10,000 INR to EUR using the latest available exchange rate.' }
]
const initial = () => {
  try { return JSON.parse(sessionStorage.getItem('wanderai-chat')) || { sessionId: null, messages: [] } }
  catch { return { sessionId: null, messages: [] } }
}

export default function App() {
  const [saved] = useState(initial)
  const [sessionId, setSessionId] = useState(saved.sessionId)
  const [messages, setMessages] = useState(saved.messages)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [failedText, setFailedText] = useState('')
  const [clearing, setClearing] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const bottom = useRef(null)
  const textarea = useRef(null)

  useEffect(() => { sessionStorage.setItem('wanderai-chat', JSON.stringify({ sessionId, messages })) }, [sessionId, messages])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, pending, error])

  async function submit(text = draft) {
    const value = text.trim()
    if (!value || pending || clearing) return
    setDraft('')
    setError('')
    setFailedText('')
    setPending(true)
    setMessages(prev => [...prev, { role: 'user', content: value }])
    try {
      const response = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: value, session_id: sessionId, history: messages.slice(-20) })
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || 'The planner could not respond.')
      setSessionId(data.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
    } catch (err) {
      setMessages(prev => prev.slice(0, -1))
      setFailedText(value)
      setError(err.message || 'Connection failed. Please try again.')
    } finally {
      setPending(false)
      textarea.current?.focus()
    }
  }

  async function clear() {
    if (pending || clearing) return
    setClearing(true)
    setError('')
    try {
      if (sessionId) {
        const response = await fetch('/api/clear', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId })
        })
        if (!response.ok) throw new Error('Could not clear the conversation. Please retry.')
      }
      setSessionId(null)
      setMessages([])
      setDraft('')
      setFailedText('')
      setMenuOpen(false)
      textarea.current?.focus()
    } catch (err) { setError(err.message || 'Could not clear the conversation.') }
    finally { setClearing(false) }
  }

  function onKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="app-shell">
      <aside className={'sidebar ' + (menuOpen ? 'open' : '')} aria-label="Planner information">
        <div className="sidebar-top">
          <a href="/" className="brand" aria-label="WanderAI home"><span className="brand-mark"><Compass size={20} strokeWidth={1.8} /></span><span>Wander<span className="brand-ai">AI</span></span></a>
          <button className="mobile-close icon-button" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X size={21} /></button>
        </div>
        <button className="new-button" onClick={clear} disabled={pending || clearing} aria-label="New conversation"><Plus size={18} />{clearing ? 'Starting anew…' : 'New conversation'}</button>
        <div className="sidebar-content">
          <p className="eyebrow">YOUR TRAVEL COMPANION</p>
          <p className="side-intro">The best journeys start with a little curiosity.</p>
          <div className="side-rule" />
          <p className="side-heading"><MapPin size={15} /> Explore worldwide</p>
          <p className="side-copy">Plan cities and regions around the world. Add a country when a place name could mean more than one destination.</p>
        </div>
        <div className="sidebar-foot"><span className="foot-dot" /> Weather forecasts cover up to 16 days. Location and weather: <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a>. Rates: <a href="https://frankfurter.dev/" target="_blank" rel="noopener noreferrer">Frankfurter</a>. Planning costs are estimates; verify prices and availability.</div>
      </aside>

      {menuOpen && <button className="scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}
      <main className="main">
        <header className="topbar">
          <button className="menu-button icon-button" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu size={22} /></button>
          <span className="topbar-title">TRIP PLANNER <span className="topbar-line" /> WORLDWIDE</span>
          <span className="topbar-note">Thoughtful travel, made simple</span>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? (
            <section className="welcome">
              <div className="welcome-kicker"><span className="kicker-line" /> YOUR NEXT CHAPTER STARTS HERE</div>
              <h1>Make room<br />for <em>wonder.</em></h1>
              <p className="welcome-copy">A thoughtful trip starts with a good question. Tell me where you dream of going, and we’ll shape the details together.</p>
              <div className="prompts-heading"><span>TRY A STARTING POINT</span><span className="prompt-line" /></div>
              <div className="prompts">
                {prompts.map(prompt => <button key={prompt.label} onClick={() => submit(prompt.text)} disabled={pending || clearing}><span>{prompt.label}</span><ArrowRight size={17} /></button>)}
              </div>
              <p className="welcome-note">Worldwide itineraries, dated weather forecasts and currency conversions. Prices and availability need separate verification.</p>
            </section>
          ) : (
            <div className="messages">
              <div className="thread-intro"><span className="thread-symbol">✳</span><div><strong>Your journey, in progress</strong><span>Ask anything as your plans take shape.</span></div></div>
              {messages.map((message, index) => <article className={'message ' + message.role} key={index}>
                <span className="message-label">{message.role === 'user' ? 'YOU' : 'WANDERAI'}</span>
                {message.role === 'assistant'
                  ? <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: PlanTable }} skipHtml>{message.content}</ReactMarkdown></div>
                  : <p>{message.content}</p>}
              </article>)}
              {pending && <div className="thinking" role="status"><span className="thinking-dots"><i /><i /><i /></span> Shaping your trip…</div>}
              <div ref={bottom} />
            </div>
          )}
        </div>

        <div className="composer-area">
          {error && <div className="error" role="alert"><span>{error}</span>{failedText && <button onClick={() => submit(failedText)} disabled={pending}>Retry message</button>}<button className="error-close" onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
          <form className="composer" onSubmit={e => { e.preventDefault(); submit() }}>
            <label className="sr-only" htmlFor="message">Ask WanderAI about your trip</label>
            <textarea id="message" ref={textarea} rows="1" value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={onKeyDown} placeholder="Where would you like to go?" maxLength={4000} disabled={pending || clearing} />
            <button type="submit" className="send-button" disabled={!draft.trim() || pending || clearing} aria-label="Send message"><Send size={18} /></button>
          </form>
          <p className="composer-hint">Press Enter to send · Shift + Enter for a new line</p>
        </div>
      </main>
    </div>
  )
}
