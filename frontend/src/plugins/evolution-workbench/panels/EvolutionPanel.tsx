import { useState, useEffect } from 'react';
import { runEvolution, fetchEvolutionCaseStats, fetchCurrentParams } from '../../../services/api';

function getParam(params: any, path: string): any {
  return path.split('.').reduce((obj: any, key: string) => obj?.[key], params);
}

const KEY_PARAMS = [
  { group: 'SC/BC', path: 'sc.volume_climax_ratio', label: '量比阈值', unit: 'x' },
  { group: 'AR', path: 'ar.min_bounce_pct', label: '最小反弹', unit: '%' },
  { group: 'ST', path: 'st.max_distance_pct', label: '最大距离', unit: '%' },
  { group: 'ST', path: 'st.volume_dryup_ratio', label: '缩量阈值', unit: 'x' },
  { group: 'Spring', path: 'spring.penetrate_min_depth', label: '穿越深度', unit: '%' },
  { group: 'Breakout', path: 'breakout.breakout_depth', label: '突破深度', unit: '%' },
];

function statsBarColor(rate: number): string {
  if (rate > 0.8) return '#26a69a';
  if (rate > 0.5) return '#42a5f5';
  return '#ff7043';
}

export function EvolutionPanel() {
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [params, setParams] = useState<any>(null);
  const [optimizeResult, setOptimizeResult] = useState<any>(null);

  useEffect(() => {
    fetchEvolutionCaseStats()
      .then((s: any) => setStats(s))
      .catch(() => setStats(null));
    fetchCurrentParams()
      .then((p: any) => setParams(p))
      .catch(() => setParams(null));
  }, []);

  const handleOptimize = async () => {
    setLoading(true);
    try {
      const res = await runEvolution();
      setOptimizeResult(res);
      // 刷新参数
      const p = await fetchCurrentParams();
      setParams(p);
    } catch (e) {
      console.error('优化失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const statsEntries = stats ? Object.entries(stats) : [];
  const totalCases = statsEntries.reduce((sum, [, v]: any) => sum + (v.total || 0), 0);

  return (
    <div style={{ padding: 8 }}>
      {/* 区域A：优化控制 */}
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>🧬 进化</div>

      <button
        onClick={handleOptimize}
        disabled={loading}
        style={{
          width: '100%', padding: '8px 12px', borderRadius: 6, border: 'none',
          cursor: loading ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: 600,
          background: 'var(--accent)', color: '#fff', opacity: loading ? 0.5 : 1,
        }}
      >
        {loading ? '优化中...' : '▶ 优化参数'}
      </button>

      {/* 优化结果 */}
      {optimizeResult && (
        <div style={{ marginTop: 8, fontSize: 11 }}>
          {optimizeResult.message ? (
            <span style={{ color: 'var(--text-muted)' }}>{optimizeResult.message}</span>
          ) : optimizeResult.params_diff ? (
            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>
                修改了 {optimizeResult.changes} 个参数 · {optimizeResult.params_version?.slice(0, 14)}
              </div>
              {Object.entries(optimizeResult.params_diff).map(([key, diff]: any) => {
                const increased = diff.after > diff.before;
                return (
                  <div key={key} style={{ display: 'flex', gap: 4, marginBottom: 2 }}>
                    <span style={{ color: 'var(--text-muted)' }}>· {key}:</span>
                    <span style={{ color: 'var(--text-muted)' }}>{typeof diff.before === 'number' ? diff.before.toFixed(3) : diff.before}</span>
                    <span style={{ color: increased ? '#ef5350' : '#26a69a' }}>→ {typeof diff.after === 'number' ? diff.after.toFixed(3) : diff.after}</span>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      )}

      <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />

      {/* 区域B：案例统计 */}
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>📊 案例库</div>

      {statsEntries.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
          暂无案例
        </div>
      )}

      {statsEntries.map(([key, s]: any) => {
        const rate = s.success_rate ?? (s.total > 0 ? s.successes / s.total : 0);
        return (
          <div key={key} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
              <span style={{ fontWeight: 600 }}>{key.toUpperCase()}</span>
              <span style={{ color: 'var(--text-muted)' }}>{s.successes}/{s.total} · {(rate * 100).toFixed(0)}%</span>
            </div>
            <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-primary)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 2,
                background: statsBarColor(rate),
                width: `${rate * 100}%`,
                transition: 'width 0.3s',
              }} />
            </div>
          </div>
        );
      })}

      {totalCases > 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
          总计: {totalCases}个案例
        </div>
      )}

      <div style={{ borderTop: '1px solid var(--border)', margin: '8px 0' }} />

      {/* 区域C：当前参数 */}
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
        ⚙ 参数 {params?.params_version ? params.params_version.slice(0, 14) : ''}
      </div>

      {!params && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
          加载中...
        </div>
      )}

      {params && (() => {
        let lastGroup = '';
        return KEY_PARAMS.map((kp) => {
          const val = getParam(params, kp.path);
          const showGroup = kp.group !== lastGroup;
          lastGroup = kp.group;
          return (
            <div key={kp.path}>
              {showGroup && (
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6, marginBottom: 2, fontWeight: 600 }}>
                  {kp.group}
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '1px 8px' }}>
                <span style={{ color: 'var(--text-muted)' }}>{kp.label}</span>
                <span>{val != null ? (typeof val === 'number' ? val.toFixed(2) : val) : '-'}{kp.unit}</span>
              </div>
            </div>
          );
        });
      })()}
    </div>
  );
}
