/** DiagnosisChatPanel — AI diagnosis chat sidebar for AnalysisPage */

import { useState, useRef, useEffect, useCallback } from "react";
import { MessageSquare, X, Trash2, Send, Loader2 } from "lucide-react";
import type { ChatMessage, AnalyzeResponse } from "../types/api";
import { sendDiagnosisChat, fetchChatHistory, clearChatHistory } from "../core/api";

interface Props {
  visible: boolean;
  onToggle: () => void;
  selectedBar?: number;
  analysisData?: AnalyzeResponse | null;
  /** Callback when AI highlights bars — parent can scroll chart */
  onHighlightBars?: (bars: number[]) => void;
}

export default function DiagnosisChatPanel({
  visible,
  onToggle,
  selectedBar,
  analysisData,
  onHighlightBars,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Load chat history from backend when panel becomes visible
  useEffect(() => {
    if (visible) {
      fetchChatHistory()
        .then((res) => {
          if (res.messages.length > 0) setMessages(res.messages);
        })
        .catch(() => {});
    }
  }, [visible]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;
    const userMsg: ChatMessage = {
      role: "user",
      content: input.trim(),
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const context: Record<string, unknown> = {};
      if (selectedBar !== undefined) {
        context.selected_bar = selectedBar;
        // 前端也传bar摘要作为双保险
        if (analysisData) {
          const bar = analysisData.bar_details.find(
            (b) => b.bar_index === selectedBar,
          );
          if (bar) {
            context.bar_summary =
              `Phase=${bar.p}, State=${bar.s}, Confidence=${bar.c}, ` +
              `StateChanged=${bar.sc}, Direction=${bar.d}`;
          }
        }
      }

      const { response } = await sendDiagnosisChat(userMsg.content, context);
      const aiMsg: ChatMessage = {
        role: "assistant",
        content: response.text,
        timestamp: Date.now(),
        suggested_params: response.suggested_params,
        highlighted_bars: response.highlighted_bars,
      };
      setMessages((prev) => [...prev, aiMsg]);
      if (response.highlighted_bars?.length && onHighlightBars) {
        onHighlightBars(response.highlighted_bars);
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `错误: ${e instanceof Error ? e.message : "请求失败"}`,
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, selectedBar, analysisData, onHighlightBars]);

  const clearChat = async () => {
    setMessages([]);
    try {
      await clearChatHistory();
    } catch {
      /* ignore */
    }
  };

  /* ---- Collapsed: vertical tab on right edge ---- */
  if (!visible) {
    return (
      <button
        onClick={onToggle}
        className="absolute right-0 top-1/2 -translate-y-1/2 z-20
          flex items-center gap-1 px-1.5 py-3
          bg-panel-surface border border-panel-border border-r-0
          rounded-l-md text-text-secondary hover:text-accent-blue
          hover:bg-panel-hover transition-colors"
        style={{ writingMode: "vertical-rl" }}
      >
        <MessageSquare size={12} />
        <span className="text-[10px] font-medium tracking-wider">AI诊断</span>
      </button>
    );
  }

  /* ---- Expanded panel ---- */
  return (
    <div className="w-80 flex-shrink-0 bg-panel-bg border-l border-panel-border
      flex flex-col h-full animate-slide-right">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2
        border-b border-panel-border bg-panel-surface">
        <div className="flex items-center gap-2">
          <MessageSquare size={14} className="text-accent-blue" />
          <span className="text-sm font-medium text-text-primary">AI诊断</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearChat}
            className="p-1 rounded text-text-muted hover:text-accent-red
              hover:bg-panel-hover transition-colors"
            title="清空对话"
          >
            <Trash2 size={12} />
          </button>
          <button
            onClick={onToggle}
            className="p-1 rounded text-text-muted hover:text-text-primary
              hover:bg-panel-hover transition-colors"
            title="关闭面板"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-text-muted text-xs mt-10 space-y-2">
            <MessageSquare size={24} className="mx-auto opacity-30" />
            <p>选中K线后输入问题</p>
            <p className="text-[10px]">
              例如: &quot;为什么这里没检测到SC？&quot;
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-panel-surface rounded-lg px-3 py-2
              text-xs text-text-secondary flex items-center gap-1.5
              border border-panel-border">
              <Loader2 size={12} className="animate-spin text-accent-blue" />
              思考中...
            </div>
          </div>
        )}
      </div>

      {/* Selected bar indicator */}
      {selectedBar !== undefined && (
        <div className="px-3 py-1 border-t border-panel-border/50
          text-[10px] text-text-muted bg-panel-surface/50">
          当前选中: Bar #{selectedBar}
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-panel-border p-2 bg-panel-surface">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="输入问题..."
            disabled={loading}
            className="flex-1 bg-panel-bg text-xs text-text-primary
              px-2.5 py-1.5 rounded border border-panel-border
              focus:border-accent-blue focus:outline-none
              disabled:opacity-50 placeholder:text-text-muted
              transition-colors"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-2.5 py-1.5 bg-accent-blue/15 text-accent-blue
              text-xs rounded hover:bg-accent-blue/25
              disabled:opacity-30 disabled:cursor-not-allowed
              transition-colors flex items-center"
          >
            <Send size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- Message bubble sub-component ---- */

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] rounded-lg px-3 py-2 text-xs leading-relaxed ${
          isUser
            ? "bg-accent-blue/15 text-text-primary border border-accent-blue/20"
            : "bg-panel-surface text-text-primary border border-panel-border"
        }`}
      >
        <p className="whitespace-pre-wrap">{msg.content}</p>

        {/* Suggested params card */}
        {msg.suggested_params && msg.suggested_params.length > 0 && (
          <div className="mt-2 pt-2 border-t border-panel-border/50 space-y-1">
            <p className="text-text-secondary text-[10px] uppercase tracking-wider">
              参数建议
            </p>
            {msg.suggested_params.map((p, j) => (
              <div
                key={j}
                className="bg-panel-bg rounded px-2 py-1 font-mono text-[10px]
                  flex items-center justify-between"
              >
                <span className="text-accent-purple">
                  {p.detector}.{p.param}
                </span>
                <span>
                  <span className="text-accent-red">{p.from}</span>
                  <span className="text-text-muted mx-1">→</span>
                  <span className="text-accent-green">{p.to}</span>
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Highlighted bars indicator */}
        {msg.highlighted_bars && msg.highlighted_bars.length > 0 && (
          <div className="mt-1.5 text-[10px] text-text-muted">
            📍 相关K线: {msg.highlighted_bars.slice(0, 5).join(", ")}
            {msg.highlighted_bars.length > 5 &&
              ` +${msg.highlighted_bars.length - 5}`}
          </div>
        )}
      </div>
    </div>
  );
}
