import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import TypingIndicator from './TypingIndicator';

function UserMessage({ content }) {
  return (
    <div className="flex items-start gap-3 justify-end animate-fade-in">
      <div
        className="
          max-w-[78%] px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed
          bg-gradient-to-br from-indigo-600 to-violet-700 text-white shadow-lg
        "
      >
        {content}
      </div>
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center text-sm border border-white/10">
        👤
      </div>
    </div>
  );
}

function AiMessage({ content }) {
  return (
    <div className="flex items-start gap-3 animate-fade-in">
      {/* Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-sm shadow-lg glow-purple">
        🌍
      </div>

      {/* Bubble */}
      <div className="glass-card px-4 py-3 max-w-[82%] text-sm">
        <div className="ai-message-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function ChatWindow({ messages, isLoading }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
      {messages.map((msg, i) =>
        msg.role === 'user'
          ? <UserMessage key={i} content={msg.content} />
          : <AiMessage key={i} content={msg.content} />
      )}
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
