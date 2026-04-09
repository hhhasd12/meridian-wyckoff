import { PluginRegistry } from './core/PluginRegistry';
import { AppShell } from './core/AppShell';
import { evolutionWorkbenchPlugin } from './plugins/evolution-workbench';

PluginRegistry.register(evolutionWorkbenchPlugin);

export function App() {
  return <AppShell />;
}
