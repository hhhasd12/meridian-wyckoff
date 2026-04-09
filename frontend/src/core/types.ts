import { ComponentType } from 'react';

export interface MeridianFrontendPlugin {
  id: string;
  name: string;
  icon: string;
  version: string;
  routes: { path: string; component: ComponentType; label?: string }[];
  onActivate?: () => void;
  onDeactivate?: () => void;
  dependencies?: string[];
}
