const DESTINATIONS = [
  { flag: '🇫🇷', city: 'Paris' },
  { flag: '🇯🇵', city: 'Tokyo' },
  { flag: '🇮🇳', city: 'Goa' },
  { flag: '🇺🇸', city: 'New York' },
  { flag: '🇮🇹', city: 'Rome' },
  { flag: '🇹🇭', city: 'Bangkok' },
  { flag: '🇦🇪', city: 'Dubai' },
  { flag: '🇧🇷', city: 'Rio' },
  { flag: '🇦🇺', city: 'Sydney' },
  { flag: '🇲🇽', city: 'Mexico City' },
  { flag: '🇬🇷', city: 'Santorini' },
  { flag: '🇲🇦', city: 'Marrakech' },
];

const FEATURES = [
  { icon: '🌍', label: 'Any city worldwide' },
  { icon: '💰', label: 'Budget estimator' },
  { icon: '🎒', label: 'Packing lists' },
  { icon: '🗺️', label: 'Itinerary planning' },
  { icon: '🍜', label: 'Local food guide' },
  { icon: '🌡️', label: 'Best time to visit' },
];

export default function Sidebar({ onClear, messageCount }) {
  return (
    <aside className="w-64 flex-shrink-0 flex flex-col glass-card m-3 mr-0 overflow-hidden">
      {/* Logo */}
      <div className="px-5 pt-5 pb-4 border-b border-white/5">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-lg shadow-lg glow-purple animate-float">
            ✈️
          </div>
          <div>
            <h1 className="font-bold text-base text-gradient">WanderAI</h1>
            <p className="text-[10px] text-slate-500 leading-tight">Global Travel Planner</p>
          </div>
        </div>
      </div>

      {/* Capabilities */}
      <div className="px-4 py-3 border-b border-white/5">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2">Capabilities</p>
        <div className="space-y-1.5">
          {FEATURES.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-slate-400">
              <span className="text-sm">{f.icon}</span>
              <span>{f.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Popular Destinations */}
      <div className="px-4 py-3 flex-1 overflow-y-auto">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2">Popular Destinations</p>
        <div className="grid grid-cols-2 gap-1.5">
          {DESTINATIONS.map((d, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-white/3 border border-white/5 text-xs text-slate-400"
            >
              <span>{d.flag}</span>
              <span className="truncate">{d.city}</span>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-slate-600 mt-2 text-center">+ any city in the world</p>
      </div>

      {/* Bottom: Stats + Clear */}
      <div className="px-4 py-3 border-t border-white/5 space-y-2">
        {messageCount > 0 && (
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Messages</span>
            <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-medium">
              {messageCount}
            </span>
          </div>
        )}
        <button
          onClick={onClear}
          className="
            w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl
            border border-white/8 text-slate-400 text-xs
            hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-400
            transition-all duration-200
          "
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          Clear conversation
        </button>

        <p className="text-center text-[10px] text-slate-600">
          Powered by Groq · LLaMA 3.3 70B
        </p>
      </div>
    </aside>
  );
}
