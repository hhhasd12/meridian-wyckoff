import { WYCKOFF_EVENTS } from '../config/wyckoffEvents';
import { useDrawingStore } from '../../../stores/drawingStore';
import { updateDrawingApi } from '../../../services/api';
import { useAppStore } from '../../../stores/appStore';

interface Props {
  drawing: any;
}

export function PropertyEditor({ drawing }: Props) {
  const { updateDrawing } = useDrawingStore();
  const { symbol } = useAppStore();

  const applyUpdate = (propUpdates: Record<string, any>) => {
    const updates = { properties: { ...drawing.properties, ...propUpdates } };
    updateDrawing(drawing.id, updates);
    updateDrawingApi(symbol, drawing.id, updates);
  };

  return (
    <div style={{ padding: 10, borderTop: '1px solid var(--border)', fontSize: 12 }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 8, fontSize: 11 }}>✏️ 编辑属性</div>

      <div style={{ marginBottom: 10 }}>
        <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 4 }}>事件类型</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
          {WYCKOFF_EVENTS.map(evt => (
            <button key={evt.id} onClick={() => applyUpdate({
              eventType: evt.id, text: evt.label, color: evt.color,
            })} title={evt.description} style={{
              padding: '2px 6px',
              borderRadius: 3,
              border: drawing.properties.eventType === evt.id ? `2px solid ${evt.color}` : `1px solid ${evt.color}30`,
              background: drawing.properties.eventType === evt.id ? `${evt.color}30` : 'transparent',
              color: evt.color,
              cursor: 'pointer',
              fontSize: 10,
              fontWeight: 600,
              fontFamily: 'monospace',
            }}>
              {evt.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 10 }}>
        <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 4 }}>文字标签</div>
        <input type="text" value={drawing.properties.text || ''} onChange={(e) => applyUpdate({ text: e.target.value })}
          placeholder="Ice / Creek / Support..."
          style={{
            width: '100%', padding: '4px 8px', borderRadius: 4,
            border: '1px solid var(--border)', background: 'var(--bg-primary)',
            color: 'var(--text-primary)', fontSize: 12, outline: 'none',
          }}
        />
      </div>

      <div>
        <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 4 }}>颜色</div>
        <div style={{ display: 'flex', gap: 4 }}>
          {['#ef5350', '#26a69a', '#42a5f5', '#ffc107', '#66bb6a', '#ff7043', '#ab47bc', '#78909c'].map(c => (
            <button key={c} onClick={() => applyUpdate({ color: c })} style={{
              width: 20, height: 20, borderRadius: '50%',
              border: drawing.properties.color === c ? '2px solid #fff' : '2px solid transparent',
              background: c, cursor: 'pointer',
            }} />
          ))}
        </div>
      </div>
    </div>
  );
}
