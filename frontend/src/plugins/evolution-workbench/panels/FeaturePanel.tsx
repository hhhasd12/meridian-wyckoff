import { useEffect, useState } from 'react';
import { fetchFeatures } from '../../../services/api';

export function FeaturePanel({ drawing }: { drawing: any }) {
  const [feat, setFeat] = useState<any>(null);

  useEffect(() => {
    fetchFeatures(drawing.symbol, drawing.id).then(setFeat);
  }, [drawing.id]);

  const f = feat?.features || {};

  const rows = [
    ['量比', f.volume_ratio ? `${f.volume_ratio}x` : '-'],
    ['下影线', f.wick_ratio ? `${(f.wick_ratio * 100).toFixed(0)}%` : '-'],
    ['实体位置', f.body_position ? `${(f.body_position * 100).toFixed(0)}%` : '-'],
    ['距支撑', f.support_distance ? `${f.support_distance}%` : '-'],
    ['恐慌度', f.effort_result?.toFixed(3) || '-'],
    ['趋势长度', f.trend_length ? `${f.trend_length}根` : '-'],
    ['趋势斜率', f.trend_slope?.toFixed(4) || '-'],
  ];

  return (
    <div style={{ padding: 8, borderTop: '1px solid var(--border)' }}>
      <h3 style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 8px' }}>
        🔬 特征 — {drawing.properties.eventType || '?'}
      </h3>

      <table style={{ width: '100%', fontSize: 11 }}>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label as string}>
              <td style={{ color: 'var(--text-muted)', padding: '3px 0' }}>{label}</td>
              <td style={{ textAlign: 'right' }}>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {f.subsequent_results && (
        <div style={{ marginTop: 8, fontSize: 10 }}>
          {Object.entries(f.subsequent_results).map(([k, v]: any) =>
            <span key={k} style={{
              marginRight: 8,
              color: v > 0 ? '#26a69a' : v < 0 ? '#ef5350' : '#888'
            }}>
              {k}: {v > 0 ? '+' : ''}{v}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
