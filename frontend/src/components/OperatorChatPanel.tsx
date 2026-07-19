import React, { useState, useRef, useEffect } from 'react';
import type { OperatorQueryResponse } from '../types';

interface ChatMessage {
  id: string;
  role: 'operator' | 'ai';
  content: string;
  confidence?: number;
  supportingData?: string[];
  degradedMode?: boolean;
  timestamp: number;
}

export function OperatorChatPanel(): React.JSX.Element {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [query, setQuery] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 200);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    // Add operator message
    const operatorMsg: ChatMessage = {
      id: `op-${Date.now()}`,
      role: 'operator',
      content: trimmed,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, operatorMsg]);
    setQuery('');
    setLoading(true);

    try {
      const res = await fetch('/api/operator/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data: OperatorQueryResponse = await res.json();

      const aiMsg: ChatMessage = {
        id: `ai-${Date.now()}`,
        role: 'ai',
        content: data.answer,
        confidence: data.confidence,
        supportingData: data.supporting_data,
        degradedMode: data.degraded_mode,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'ai',
        content: `Unable to process query: ${errorMessage}`,
        confidence: 0,
        degradedMode: true,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-emerald-400';
    if (score >= 0.6) return 'text-amber-400';
    return 'text-red-400';
  };

  return (
    <>
      {/* Toggle Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Toggle AI operator chat assistance panel"
        aria-expanded={isOpen}
        className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-2xl shadow-2xl transition-all duration-300 ${
          isOpen
            ? 'bg-slate-800 border border-slate-700 text-slate-300'
            : 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-500 hover:to-purple-500'
        }`}
        title="Open AI Operator Chat"
        id="operator-chat-toggle"
      >
        {isOpen ? (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <>
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <span className="text-sm font-bold">Ask AI</span>
          </>
        )}
      </button>

      {/* Chat Panel */}
      <div
        className={`fixed bottom-20 right-6 z-40 w-96 max-h-[520px] rounded-2xl border border-slate-800 bg-slate-950/95 backdrop-blur-xl shadow-2xl flex flex-col transition-all duration-300 ${
          isOpen ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4 pointer-events-none'
        }`}
        id="operator-chat-panel"
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
          <div className="relative">
            <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
            AI Operations Assistant
          </span>
          <span className="ml-auto text-[9px] text-slate-600 font-mono">5s throttle</span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[200px] max-h-[350px]">
          {messages.length === 0 && (
            <div className="text-center py-8">
              <svg className="w-8 h-8 text-slate-700 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <p className="text-xs text-slate-600 leading-relaxed">
                Ask about the venue state, crowd trends,<br />or get tactical recommendations.
              </p>
              <div className="mt-3 space-y-1.5">
                {['Which zone is most at risk?', 'What\'s the safest exit path?', 'Summarize current status'].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setQuery(suggestion);
                      inputRef.current?.focus();
                    }}
                    className="block w-full text-left text-[11px] text-slate-500 hover:text-indigo-400 bg-slate-900/50 hover:bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800/50 transition-colors"
                  >
                    "{suggestion}"
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'operator' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 ${
                  msg.role === 'operator'
                    ? 'bg-indigo-600/30 border border-indigo-500/20 text-slate-200'
                    : msg.degradedMode
                    ? 'bg-amber-950/30 border border-amber-500/20 text-amber-200'
                    : 'bg-slate-900/80 border border-slate-800 text-slate-300'
                }`}
              >
                <p className="text-xs leading-relaxed">{msg.content}</p>

                {/* Supporting Data */}
                {msg.role === 'ai' && msg.supportingData && msg.supportingData.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-slate-800/50">
                    <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">Supporting Data</span>
                    <ul className="mt-1 space-y-0.5">
                      {msg.supportingData.map((point, i) => (
                        <li key={i} className="text-[10px] text-slate-400 flex items-start gap-1">
                          <span className="text-indigo-500 mt-0.5 shrink-0">•</span>
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Confidence */}
                {msg.role === 'ai' && msg.confidence !== undefined && (
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <span className={`text-[9px] font-bold ${getConfidenceColor(msg.confidence)}`}>
                      {Math.round(msg.confidence * 100)}% confidence
                    </span>
                    {msg.degradedMode && (
                      <span className="text-[9px] text-amber-400 font-bold">• DEGRADED</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-1.5">
                  <div className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="h-1.5 w-1.5 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className="px-4 py-3 border-t border-slate-800">
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              aria-label="Tournament operator natural language query input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about venue state..."
              maxLength={280}
              disabled={loading}
              className="flex-1 bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 disabled:opacity-50 transition-colors"
              id="operator-chat-input"
            />
            <button
              type="button"
              aria-label="Submit query to AI decision engine"
              onClick={(e) => { void handleSubmit(e as unknown as React.FormEvent); }}
              disabled={!query.trim() || loading}
              className="shrink-0 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl px-3 py-2 transition-colors flex items-center gap-1.5"
              id="operator-chat-send"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
              <span className="text-xs font-semibold">Send</span>
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
