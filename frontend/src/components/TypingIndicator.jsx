export default function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-fade-in">
      {/* Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-sm shadow-lg glow-purple">
        🌍
      </div>

      {/* Bubble */}
      <div className="glass-card px-4 py-3 max-w-[80px]">
        <div className="flex items-center gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
