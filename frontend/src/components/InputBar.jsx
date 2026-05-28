import { useState, useRef } from 'react';

export default function InputBar({ onSend, isLoading }) {
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e) => {
    setValue(e.target.value);
    // Auto-resize
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 140) + 'px';
    }
  };

  return (
    <div className="px-4 py-3 border-t border-white/5">
      <div
        className="
          flex items-end gap-3 glass-card px-4 py-3
          focus-within:border-indigo-500/50 focus-within:shadow-[0_0_20px_rgba(99,102,241,0.2)]
          transition-all duration-300
        "
      >
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about any destination — Paris, Tokyo, Machu Picchu, Zanzibar..."
          rows={1}
          disabled={isLoading}
          className="
            flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500
            resize-none outline-none leading-relaxed min-h-[24px] max-h-[140px]
            disabled:opacity-50 disabled:cursor-not-allowed
          "
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!value.trim() || isLoading}
          className="
            flex-shrink-0 w-9 h-9 rounded-xl
            bg-gradient-to-br from-indigo-500 to-violet-600
            flex items-center justify-center text-white
            hover:from-indigo-400 hover:to-violet-500 hover:scale-105
            disabled:opacity-40 disabled:cursor-not-allowed disabled:scale-100
            transition-all duration-200 shadow-lg
          "
          title="Send (Enter)"
        >
          {isLoading ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          )}
        </button>
      </div>
      <p className="text-center text-xs text-slate-600 mt-2">
        Press <kbd className="px-1 py-0.5 rounded bg-white/5 border border-white/10 text-slate-400 text-[10px]">Enter</kbd> to send &middot; <kbd className="px-1 py-0.5 rounded bg-white/5 border border-white/10 text-slate-400 text-[10px]">Shift+Enter</kbd> for new line
      </p>
    </div>
  );
}
