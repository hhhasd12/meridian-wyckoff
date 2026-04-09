import { useState } from 'react';
import { Sidebar } from './Sidebar';
import { PluginRegistry } from './PluginRegistry';

export function AppShell() {
  const plugins = PluginRegistry.getAll();
  const [activeId, setActiveId] = useState(plugins[0]?.id || '');
  const active = PluginRegistry.get(activeId);
  const Page = active?.routes[0]?.component;

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-primary)' }}>
      <Sidebar plugins={plugins} activeId={activeId}
        onSwitch={(id) => {PluginRegistry.get(activeId)?.onDeactivate?.();
          setActiveId(id);
          PluginRegistry.get(id)?.onActivate?.();
        }} />
      <main style={{ flex: 1, overflow: 'hidden' }}>
        {Page && <Page />}
      </main>
    </div>
  );
}
