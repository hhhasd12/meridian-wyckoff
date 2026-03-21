import { Bot } from "lucide-react";

export default function AdvisorTab() {
  // Advisor analysis will come from WS advisor_analysis messages
  // For now, placeholder
  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-2 text-xs text-text-secondary">
        <Bot size={14} />
        <span>AI Advisor Analysis</span>
      </div>
      <div className="text-text-muted text-xs italic">
        Waiting for advisor analysis data...
      </div>
      <div className="text-[10px] text-text-muted">
        The AI advisor provides strategic recommendations based on current
        market state, Wyckoff phase analysis, and evolution results.
      </div>
    </div>
  );
}
