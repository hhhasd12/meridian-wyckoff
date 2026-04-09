import { useDrawingStore } from '../../../stores/drawingStore';
import { PropertyEditor } from '../components/PropertyEditor';

const EVENT_COLORS: Record<string, string> = {
  SC: '#ef5350', BC: '#ef5350',
  AR: '#26a69a',
  ST: '#42a5f5',
  Spring: '#ffc107', UTAD: '#ffc107',
  SOS: '#66bb6a', SOW: '#ff7043',
  JOC: '#ab47bc'
};

function formatTime(ts: number): string {
  const ms = ts > 1e12 ? ts : ts * 1000;
  return new Date(ms).toLocaleDateString();
}

export function AnnotationPanel() {
  const { drawings, selectedId, selectDrawing } = useDrawingStore();

  const sorted = Array.from(drawings.values())
    .filter(d => d.properties.eventType)
    .sort((a, b) => a.points[0]?.time - b.points[0]?.time);

  const selectedDrawing = selectedId ? drawings.get(selectedId) : null;

  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
        📋 标注管理 ({sorted.length})
      </div>

      {sorted.map(d => (
        <button key={d.id} onClick={() => selectDrawing(d.id)} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 8px', borderRadius: 4,
          border: 'none', cursor: 'pointer',
          width: '100%', textAlign: 'left', fontSize: 12,
          background: d.id === selectedId ? 'var(--accent-dim)' : 'transparent',
          color: 'var(--text-primary)'
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: EVENT_COLORS[d.properties.eventType] || '#888'
          }} />
          <span style={{ fontWeight: 600 }}>{d.properties.eventType}</span>
          <span style={{ color: 'var(--text-muted)' }}>
            {d.points[0] ? formatTime(d.points[0].time) : '-'}
          </span>
          <span style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
            {d.properties.timeframe}
          </span>
        </button>
      ))}

      {!sorted.length && (
        <p style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
          暂无标注
        </p>
      )}

      {selectedDrawing && <PropertyEditor drawing={selectedDrawing} />}
    </div>
  );
}
