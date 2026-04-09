import { MeridianFrontendPlugin } from '../../core/types';
import { EvolutionPage } from './EvolutionPage';

export const evolutionWorkbenchPlugin: MeridianFrontendPlugin = {
  id: 'evolution-workbench',
  name: '进化工作台',
  icon: '📐',
  version: '0.1.0',
  routes: [{ path: '/evolution', component: EvolutionPage }],
};
