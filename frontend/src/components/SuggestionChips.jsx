const SUGGESTIONS = [
  { icon: "🗼", text: "Plan a 5-day trip to Paris on a mid budget" },
  { icon: "🏯", text: "Best things to do in Kyoto, Japan" },
  { icon: "🌴", text: "Beach vacation in Bali — what to pack?" },
  { icon: "🗽", text: "Estimate costs for 1 week in New York City" },
  { icon: "🦁", text: "Plan a safari trip to Kenya" },
  { icon: "🏔️", text: "Budget trekking trip to Patagonia, Argentina" },
  { icon: "🕌", text: "What to see in Istanbul, Turkey?" },
  { icon: "🐨", text: "2 weeks in Australia — itinerary ideas" },
];

export default function SuggestionChips({ onSelect }) {
  return (
    <div className="flex flex-wrap gap-2 justify-center max-w-2xl mx-auto">
      {SUGGESTIONS.map((s, i) => (
        <button
          key={i}
          onClick={() => onSelect(s.text)}
          className="
            flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm
            bg-white/5 border border-white/10 text-slate-300
            hover:bg-indigo-500/20 hover:border-indigo-400/40 hover:text-indigo-200
            transition-all duration-200 cursor-pointer
            animate-fade-in
          "
          style={{ animationDelay: `${i * 60}ms`, animationFillMode: 'both' }}
        >
          <span>{s.icon}</span>
          <span>{s.text}</span>
        </button>
      ))}
    </div>
  );
}
