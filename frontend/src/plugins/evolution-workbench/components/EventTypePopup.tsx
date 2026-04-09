import { getSelectableEvents, getEventsByCategory, WyckoffEventDef } from '../config/wyckoffEvents';

interface Props {
  position: { x: number; y: number };
  onSelect: (event: WyckoffEventDef) => void;
  onCancel: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  both: '通用',
  accumulation: '吸筹',
  distribution: '派发',
  trend: '趋势',
  general: '标记',
  custom: '自定义',
};

const CATEGORY_ORDER = ['both', 'accumulation', 'distribution', 'trend', 'general'] as const;

export function EventTypePopup({ position, onSelect, onCancel }: Props) {
  const left = Math.min(position.x, window.innerWidth - 320);
  const top = Math.min(position.y + 10, window.innerHeight - 360);

  return (
    <>
      <div onClick={onCancel} style={{
        position: 'fixed', inset: 0, zIndex: 999, background: 'transparent',
      }} />
      <div style={{
        position: 'fixed', left, top,
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 10,
        zIndex: 1000,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        minWidth: 300,
        maxHeight: '80vh',
        overflowY: 'auto',
      }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, paddingLeft: 4 }}>
          选择事件类型
        </div>
        {CATEGORY_ORDER.map(cat => {
          const events = getEventsByCategory(cat);
          if (!events.length) return null;
          return (
            <div key={cat} style={{ marginBottom: 8 }}>
              <div style={{
                fontSize: 10, color: 'var(--text-muted)', marginBottom: 4,
                paddingLeft: 2, textTransform: 'uppercase', letterSpacing: 1,
              }}>
                {CATEGORY_LABELS[cat]}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                {events.map(evt => (
                  <button key={evt.id} onClick={() => onSelect(evt)} title={evt.description} style={{
                    padding: '4px 8px',
                    borderRadius: 4,
                    border: `1px solid ${evt.color}40`,
                    background: `${evt.color}15`,
                    color: evt.color,
                    cursor: 'pointer',
                    fontSize: 11,
                    fontWeight: 600,
                    fontFamily: 'monospace',
                  }}>
                    {evt.label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
