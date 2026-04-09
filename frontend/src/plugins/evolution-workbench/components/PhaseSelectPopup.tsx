import { WYCKOFF_PHASES, WyckoffPhaseDef } from '../config/wyckoffEvents';

interface Props {
  position: { x: number; y: number };
  onSelect: (phase: WyckoffPhaseDef) => void;
  onCancel: () => void;
}

export function PhaseSelectPopup({ position, onSelect, onCancel }: Props) {
  const left = Math.min(position.x, window.innerWidth - 200);
  const top = Math.min(position.y + 10, window.innerHeight - 240);

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
        padding: 8,
        zIndex: 1000,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, paddingLeft: 4 }}>
          选择阶段
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {WYCKOFF_PHASES.map(phase => (
            <button key={phase.id} onClick={() => onSelect(phase)} title={phase.description} style={{
              padding: '6px 12px',
              borderRadius: 4,
              border: `1px solid ${phase.color}40`,
              background: `${phase.color}15`,
              color: phase.color,
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
              textAlign: 'left',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <span>{phase.label}</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{phase.description}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
