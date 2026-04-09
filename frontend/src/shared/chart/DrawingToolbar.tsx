const TOOLS = [
  { id: 'cursor', icon: '↗', key: '1', label: '选择' },
  { id: 'trend_line', icon: '╱', key: '2', label: '趋势线' },
  { id: 'parallel_channel', icon: '▱', key: '3', label: '平行通道' },
  { id: 'horizontal_line', icon: '─', key: '4', label: '水平线' },
  { id: 'vertical_line', icon: '│', key: '5', label: '垂直线' },
  { id: 'callout', icon: '💬', key: '6', label: '事件气泡' },
  { id: 'phase_marker', icon: '🏷', key: '7', label: '阶段标记' },
];

export function DrawingToolbar({ currentTool, onToolChange }: {
  currentTool: string;
  onToolChange: (tool: string) => void;
}) {
  return (
    <div style={{
      width: 48, background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', paddingTop: 8, gap: 2
    }}>
      {TOOLS.map(t => (
        <button key={t.id} onClick={() => onToolChange(t.id)}
          title={`${t.label} (${t.key})`}
          style={{
            width: 36, height: 36, borderRadius: 6, border: 'none',
            cursor: 'pointer', fontSize: 16,
            background: t.id === currentTool ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
          {t.icon}
        </button>
      ))}
    </div>
  );
}
