import { MeridianFrontendPlugin } from './types';

class Registry {
  private plugins = new Map<string, MeridianFrontendPlugin>();
  register(p: MeridianFrontendPlugin) { this.plugins.set(p.id, p); }
  getAll() { return Array.from(this.plugins.values()); }
  get(id: string) { return this.plugins.get(id); }
}
export const PluginRegistry = new Registry();
