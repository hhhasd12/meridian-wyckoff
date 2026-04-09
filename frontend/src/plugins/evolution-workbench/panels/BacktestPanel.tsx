import { useState, useEffect } from 'react';
import { useAppStore } from '../../../stores/appStore';
import { runBacktest, fetchBacktestHistory, fetchBacktestResult } from '../../../services/api';

const EVENT_COLORS: Record<string, string> = {
  sc: '#ef5350', bc: '#ef5350',
  ar: '#26a69a',
  st: '#42a5f5',
  spring: '#ffc107', utad: '#ffc107',
  sos: '#66bb6a', sow: '#ff7043',
  joc: '#ab47bc',
};

function resultIcon(r: string): { icon: string; color: string } {
  if (r === 'success') return { icon: '✓', color: '#26a69a' };
  if (r === 'failed') return { icon: '✗', color: '#ef5350' };
  return { icon: '○', color: '#787b86' };
}

export function BacktestPanel() {
  const { symbol, timeframe } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [view, setView] = useState<'trigger' | 'detail'>('trigger');

  // 挂载时加载历史
  useEffect(() => {
    fetchBacktestHistory()
      .then((h: any) => setHistory(h.runs || []))
      .catch(() => setHistory([]));
  }, []);

  const handleRun = async () => {
    setLoading(true);
    try {
      const res = await runBacktest(symbol, timeframe);
      setResult(res);
      const hist = await fetchBacktestHistory();
      setHistory(hist.runs || []);
    } catch (e) {
      console.error('回测失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (runId: string) => {
    try {
      const d = await fetchBacktestResult(runId);
      setDetail(d);
      setView('detail');
    } catch (e) {
      console.error('加载详情失败:', e);
    }
  };

  const handleEventClick = (barIndex: number) => {
    useAppStore.getState().setFocusBarIndex(barIndex);
  };

  const score = result?.score;

  // 详情视图
  if (view === 'detail' && detail) {
    const events: any[] = detail.result?.events || [];
    const transitions: any[] = detail.result?.transitions || [];

    return (
      <div style={{ padding: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <button
            onClick={() => { setView('trigger'); setDetail(null); }}
            style={{
              border: 'none', background: 'transparent',
              color: 'var(--accent)', cursor: 'pointer', fontSize: 12,
            }}
          >
            ← 返回
          </button>
          <span style={{ fontSize: 12, fontWeight: 600 }}>{detail.run_id?.slice(0, 10)}</span>
        </div>

        <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />

        {/* 事件列表 */}
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
          事件列表 ({events.length})
        </div>
        {events.length === 0 && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>
            暂无事件
          </div>
        )}
        {events.map((evt: any, i: number) => {
          const color = EVENT_COLORS[evt.event_type] || '#888';
          const { icon, color: rColor } = resultIcon(evt.event_result);
          return (
            <button
              key={i}
              onClick={() => handleEventClick(evt.bar_index)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '4px 6px', fontSize: 11, borderRadius: 3,
                border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left',
                background: 'transparent', color: 'var(--text-primary)',
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ fontWeight: 600, color }}>{(evt.event_type || '').toUpperCase()}</span>
              <span style={{ color: 'var(--text-muted)' }}>bar:{evt.bar_index}</span>
              <span style={{ color: 'var(--text-muted)' }}>
                vol:{evt.volume_ratio != null ? evt.volume_ratio.toFixed(1) + 'x' : '-'}
              </span>
              <span style={{ color: rColor }}>{icon}</span>
            </button>
          );
        })}

        <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />

        {/* 阶段转换 */}
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
          阶段转换 ({transitions.length})
        </div>
        {transitions.map((t: any, i: number) => (
          <div key={i} style={{ fontSize: 11, padding: '3px 6px', color: 'var(--text-muted)' }}>
            bar:{t.bar_index} {t.from_phase || 'none'} → {t.to_phase}
            {t.trigger_rule ? ` (${t.trigger_rule})` : ''}
          </div>
        ))}
      </div>
    );
  }

  // 主视图
  return (
    <div style={{ padding: 8 }}>
      {/* 区域A：触发区 */}
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>🧪 回测</div>

      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
        {symbol} · {timeframe}
      </div>

      <button
        onClick={handleRun}
        disabled={loading}
        style={{
          width: '100%', padding: '8px 12px', borderRadius: 6, border: 'none',
          cursor: loading ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: 600,
          background: 'var(--accent)', color: '#fff', opacity: loading ? 0.5 : 1,
        }}
      >
        {loading ? '运行中...' : '▶ 运行回测'}
      </button>

      {/* 区域B：评分卡片 */}
      {score && (
        <div style={{ marginTop: 10 }}>
          <ScoreRow label="检测率" value={score.detection_rate} color="#26a69a" />
          <ScoreRow label="误报率" value={score.false_positive_rate} color="#ef5350" />
          <ScoreRow label="阶段准确" value={score.phase_accuracy} color="#42a5f5" />

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '2px 0' }}>
            <span style={{ color: 'var(--text-muted)' }}>平均偏移</span>
            <span>{score.avg_time_offset != null ? score.avg_time_offset.toFixed(1) + ' bars' : '-'}</span>
          </div>

          <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />

          <div style={{ display: 'flex', gap: 8, fontSize: 11, flexWrap: 'wrap' }}>
            <span style={{ color: '#26a69a' }}>匹配 {score.matched_count ?? '-'}</span>
            <span style={{ color: '#ef5350' }}>漏报 {score.missed_count ?? '-'}</span>
            <span style={{ color: '#ff7043' }}>误报 {score.false_positive_count ?? '-'}</span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
            标注 {score.total_annotations ?? '-'} · 引擎 {score.total_engine_events ?? '-'} · 共{result?.total_bars ?? '-'}bar
          </div>

          {score.note && (
            <div style={{ fontSize: 10, color: '#ffc107', marginTop: 4 }}>⚠ {score.note}</div>
          )}
        </div>
      )}

      <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />

      {/* 区域C：历史列表 */}
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
        📜 历史 ({history.length})
      </div>

      {history.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
          暂无历史
        </div>
      )}

      {history.map((run: any) => {
        const s = run.score_summary;
        return (
          <button
            key={run.run_id}
            onClick={() => handleViewDetail(run.run_id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 8px', borderRadius: 4, border: 'none',
              cursor: 'pointer', width: '100%', textAlign: 'left', fontSize: 11,
              background: 'transparent', color: 'var(--text-primary)',
            }}
          >
            <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>
              {run.run_id?.slice(0, 8)}
            </span>
            {run.timeframe && (
              <span style={{ color: 'var(--text-muted)' }}>{run.timeframe}</span>
            )}
            <span style={{ marginLeft: 'auto', color: '#26a69a' }}>
              检{s?.detection_rate != null ? (s.detection_rate * 100).toFixed(0) + '%' : '-'}
            </span>
            <span style={{ color: '#ef5350' }}>
              误{s?.false_positive_rate != null ? (s.false_positive_rate * 100).toFixed(0) + '%' : '-'}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function ScoreRow({ label, value, color }: { label: string; value: number | undefined; color: string }) {
  const pct = value != null ? value * 100 : 0;
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span>{value != null ? pct.toFixed(1) + '%' : '-'}</span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-primary)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 2, background: color,
          width: `${Math.min(pct, 100)}%`, transition: 'width 0.3s',
        }} />
      </div>
    </div>
  );
}
