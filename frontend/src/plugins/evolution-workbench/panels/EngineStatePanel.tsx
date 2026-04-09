import { useState, useEffect } from 'react';
import { useAppStore } from '../../../stores/appStore';
import { fetchEngineState } from '../../../services/api';

const EVENT_COLORS: Record<string, string> = {
  sc: '#ef5350', bc: '#ef5350',
  ar: '#26a69a',
  st: '#42a5f5',
  spring: '#ffc107', utad: '#ffc107',
  sos: '#66bb6a', sow: '#ff7043',
  joc: '#ab47bc',
};

const DIRECTION_COLORS: Record<string, string> = {
  bullish: '#26a69a',
  bearish: '#ef5350',
  neutral: '#787b86',
};

const DIRECTION_ARROWS: Record<string, string> = {
  bullish: '▲',
  bearish: '▼',
  neutral: '●',
};

const STRUCTURE_COLORS: Record<string, string> = {
  accumulation: '#26a69a20',
  distribution: '#ef535020',
  unknown: '#787b8620',
};

const PHASE_LABELS: Record<string, string> = {
  a: 'Phase A', b: 'Phase B', c: 'Phase C', d: 'Phase D', e: 'Phase E',
  none: 'No Phase',
};

function confidenceColor(v: number): string {
  if (v > 0.7) return '#26a69a';
  if (v > 0.4) return '#42a5f5';
  return '#ff7043';
}

function resultIcon(r: string): { icon: string; color: string } {
  if (r === 'success') return { icon: '✓', color: '#26a69a' };
  if (r === 'failed') return { icon: '✗', color: '#ef5350' };
  return { icon: '○', color: '#787b86' };
}

export function EngineStatePanel() {
  const { symbol, timeframe } = useAppStore();
  const [state, setState] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadState = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await fetchEngineState(symbol, timeframe);
      setState(s);
    } catch (e: any) {
      setError(e.message || '加载失败');
      setState(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadState(); }, [symbol, timeframe]);

  const direction = state?.direction || 'neutral';
  const structure = state?.structure_type || 'unknown';
  const confidence = state?.confidence ?? 0;
  const phase = state?.current_phase || 'none';
  const events: any[] = state?.recent_events || [];

  return (
    <div style={{ padding: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>⚙ 引擎状态</span>
        <button
          onClick={loadState}
          disabled={loading}
          style={{
            padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)',
            background: 'var(--bg-primary)', color: 'var(--text-primary)',
            cursor: loading ? 'not-allowed' : 'pointer', fontSize: 11,
            opacity: loading ? 0.5 : 1,
          }}
        >
          刷新
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
          {error}
        </div>
      )}

      {!error && !state && !loading && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
          引擎未运行，请先运行回测或启动引擎
        </div>
      )}

      {loading && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
          加载中...
        </div>
      )}

      {state && !error && (
        <>
          {/* 区域A：状态概览 */}
          <div style={{
            textAlign: 'center', padding: '12px 0',
            background: STRUCTURE_COLORS[structure] || '#787b8620',
            borderRadius: 6, marginBottom: 8,
          }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
              {PHASE_LABELS[phase] || phase.toUpperCase()}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              {(structure || 'UNKNOWN').toUpperCase()}
            </div>
            <div style={{
              fontSize: 13, fontWeight: 600,
              color: DIRECTION_COLORS[direction],
              marginTop: 4,
            }}>
              {DIRECTION_ARROWS[direction]} {direction.toUpperCase()}
            </div>
          </div>

          {/* 信心值进度条 */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
              <span style={{ color: 'var(--text-muted)' }}>信心</span>
              <span>{(confidence * 100).toFixed(0)}%</span>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-primary)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 2,
                background: confidenceColor(confidence),
                width: `${confidence * 100}%`,
                transition: 'width 0.3s',
              }} />
            </div>
          </div>

          {/* K线数 + 参数版本 */}
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            <span>K线: {state.bar_count ?? '-'} 根</span>
            <span>参数: {(state.params_version || '-').slice(0, 12)}</span>
          </div>

          {/* 分隔线 */}
          <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />

          {/* 区域B：最近事件 */}
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            📡 最近事件 ({events.length})
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
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '4px 6px', fontSize: 11, borderRadius: 3,
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
                <span style={{ fontWeight: 600, color }}>{(evt.event_type || '').toUpperCase()}</span>
                <span style={{ color: 'var(--text-muted)' }}>bar:{evt.start_bar ?? evt.end_bar ?? '-'}</span>
                <span style={{ color: rColor }}>{icon}</span>
                <span style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
                  {(evt.confidence != null ? (evt.confidence * 100).toFixed(0) + '%' : '')}
                </span>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
