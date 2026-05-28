import { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import InputBar from './components/InputBar';
import SuggestionChips from './components/SuggestionChips';

// Combined Vercel deploy: API is on same domain, so API_BASE = '' (relative /api/...)
// Separate deploy: set VITE_API_URL to your backend URL in Vercel env vars
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export default function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = async (text) => {
    if (!text.trim() || isLoading) return;
    setError(null);

    // Optimistically add user message
    const userMsg = { role: 'user', content: text };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          // Send history excluding the latest user message (backend appends it)
          history: messages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      setMessages([...updatedMessages, { role: 'assistant', content: data.response }]);
    } catch (err) {
      const isConfigError = !import.meta.env.VITE_API_URL && err.message.includes('405');
      const hint = isConfigError
        ? '\n\n> **Deployment fix:** Set `VITE_API_URL` in Vercel → Settings → Environment Variables to your Railway backend URL, then redeploy.'
        : '\n\n> Make sure the backend is running: `python start.py`';
      setError(err.message);
      setMessages([
        ...updatedMessages,
        {
          role: 'assistant',
          content: `⚠️ **Error:** ${err.message}${hint}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setError(null);
  };

  const isEmpty = messages.length === 0;

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{
        background: 'radial-gradient(ellipse at 20% 50%, rgba(99,102,241,0.08) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(124,58,237,0.06) 0%, transparent 60%), #070b14',
      }}
    >
      {/* Sidebar */}
      <Sidebar onClear={clearChat} messageCount={messages.length} />

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col min-w-0 m-3 glass-card overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-white/5 flex-shrink-0">
          <div>
            <h2 className="font-semibold text-slate-100 text-sm">Travel Planner</h2>
            <p className="text-xs text-slate-500">Ask about any destination worldwide</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs text-jade-400 bg-jade-500/10 px-2.5 py-1 rounded-full border border-jade-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-jade-400 animate-pulse-slow" />
              Online
            </span>
          </div>
        </header>

        {/* Empty state */}
        {isEmpty && (
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-8 text-center animate-slide-up">
            {/* Hero */}
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-600/20 border border-indigo-500/20 flex items-center justify-center text-4xl mb-5 animate-float">
              🌍
            </div>
            <h3 className="text-2xl font-bold text-gradient mb-2">Plan Your Dream Trip</h3>
            <p className="text-slate-400 text-sm max-w-md mb-8 leading-relaxed">
              Ask me anything about any city in the world — attractions, budget, packing,
              itineraries, local tips, visa info, and more.
            </p>

            {/* Suggestion chips */}
            <SuggestionChips onSelect={sendMessage} />
          </div>
        )}

        {/* Chat messages */}
        {!isEmpty && (
          <ChatWindow messages={messages} isLoading={isLoading} />
        )}

        {/* Input bar */}
        <InputBar onSend={sendMessage} isLoading={isLoading} />
      </main>
    </div>
  );
}
