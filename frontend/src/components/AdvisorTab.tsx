import { useEffect, useState } from "react";
import {
  Bot,
  RefreshCw,
  BarChart3,
  AlertTriangle,
  Wrench,
  BookOpen,
} from "lucide-react";
import { fetchAdvisorLatest } from "../core/api";
import { useStore } from "../core/store";

/** 结构化展示区块 */
function AnalysisSection({
  icon: Icon,
  title,
  content,
  color,
}: {
  icon: typeof BarChart3;
  title: string;
  content: string | undefined | null;
  color: string;
}) {
  if (!content) return null;

  return (
    <div className="space-y-1">
      <div className={`flex items-center gap-1.5 text-xs font-medium ${color}`}>
        <Icon size={12} />
        <span>{title}</span>
      </div>
      <div className="text-sm text-text-primary leading-relaxed pl-4 whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}

export default function AdvisorTab() {
  const advisorAnalysis = useStore((s) => s.advisorAnalysis);
  const setAdvisorAnalysis = useStore((s) => s.setAdvisorAnalysis);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAdvisorLatest()
      .then((resp) => {
        if (cancelled) return;
        setAdvisorAnalysis(resp.analysis);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message ?? "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [setAdvisorAnalysis]);

  if (loading) {
    return (
      <div className="p-3 flex items-center gap-2 text-text-muted text-sm">
        <RefreshCw size={14} className="animate-spin" />
        <span>加载顾问分析中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3 text-accent-red text-sm">
        加载失败: {error}
      </div>
    );
  }

  if (!advisorAnalysis) {
    return (
      <div className="p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm text-text-secondary">
          <Bot size={14} />
          <span>AI 顾问分析</span>
        </div>
        <div className="text-text-muted text-sm italic">
          暂无顾问分析数据
        </div>
        <div className="text-xs text-text-muted leading-relaxed">
          AI 顾问会根据当前市场状态、威科夫阶段和进化结果提供策略建议。
          需要至少完成一个进化周期后才会生成分析。
        </div>
      </div>
    );
  }

  // Extract structured fields
  const analysis = advisorAnalysis.analysis as string | undefined;
  const plateauWarning = advisorAnalysis.plateau_warning as string | undefined;
  const mutationAdvice = advisorAnalysis.mutation_advice as string | undefined;
  const mistakeSummary = advisorAnalysis.mistake_summary as string | undefined;

  // Remaining fields (generic key-value)
  const structuredKeys = new Set([
    "analysis",
    "plateau_warning",
    "mutation_advice",
    "mistake_summary",
  ]);
  const otherEntries = Object.entries(advisorAnalysis).filter(
    ([key]) => !structuredKeys.has(key),
  );

  const hasStructured =
    analysis || plateauWarning || mutationAdvice || mistakeSummary;

  return (
    <div className="p-3 space-y-3 overflow-auto h-full">
      {/* Header */}
      <div className="flex items-center gap-2 text-sm text-text-secondary">
        <Bot size={14} />
        <span>AI 顾问分析</span>
        <span className="ml-auto badge badge-green text-xs">已加载</span>
      </div>

      {/* Structured sections */}
      {hasStructured ? (
        <div className="space-y-3">
          <AnalysisSection
            icon={BarChart3}
            title="轮次分析"
            content={analysis}
            color="text-accent-blue"
          />
          <AnalysisSection
            icon={AlertTriangle}
            title="局部最优警告"
            content={plateauWarning}
            color="text-accent-yellow"
          />
          <AnalysisSection
            icon={Wrench}
            title="变异建议"
            content={mutationAdvice}
            color="text-accent-purple"
          />
          <AnalysisSection
            icon={BookOpen}
            title="错题本摘要"
            content={mistakeSummary}
            color="text-accent-cyan"
          />
        </div>
      ) : null}

      {/* Generic key-value fallback */}
      {otherEntries.length > 0 && (
        <div className="space-y-1.5 pt-2 border-t border-panel-border/50">
          {otherEntries.map(([key, value]) => (
            <div
              key={key}
              className="flex justify-between text-[13px] border-b border-panel-border/30 pb-1"
            >
              <span className="text-text-secondary truncate mr-2">{key}</span>
              <span className="text-accent-cyan font-mono shrink-0 text-right max-w-[60%] truncate">
                {typeof value === "object" && value !== null
                  ? JSON.stringify(value).slice(0, 80)
                  : String(value ?? "—")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
