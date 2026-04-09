export function Sidebar({ plugins, activeId, onSwitch }: {
  plugins: import('./types').MeridianFrontendPlugin[];
  activeId: string;
  onSwitch: (id: string) => void;
}) {
  return (
    <nav style={{
      width: 56, background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', paddingTop: 12, gap: 4
    }}>
      {plugins.map(p => (
        <button key={p.id} onClick={() => onSwitch(p.id)} title={p.name}
          style={{
            width: 40, height: 40, borderRadius: 8, border: 'none',
            fontSize: 20, cursor: 'pointer',
            background: p.id === activeId ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
          {p.icon}
        </button>
      ))}
    </nav>
  );
}
