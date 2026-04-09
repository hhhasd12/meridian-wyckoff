export interface WyckoffEventDef {
  id: string;
  label: string;
  color: string;
  category: 'accumulation' | 'distribution' | 'both' | 'trend' | 'general' | 'custom';
  description: string;
}

export const WYCKOFF_EVENTS: WyckoffEventDef[] = [
  // ── 通用事件 ──
  { id: 'PS', label: 'PS', color: '#78909c', category: 'both', description: '初始支撑/供应' },
  { id: 'AR', label: 'AR', color: '#26a69a', category: 'both', description: '自动反弹/回落' },
  { id: 'ST', label: 'ST', color: '#42a5f5', category: 'both', description: '二次测试' },

  // ── 吸筹阶段 ──
  { id: 'SC', label: 'SC', color: '#ef5350', category: 'accumulation', description: '抛售高潮' },
  { id: 'Spring', label: 'Spring', color: '#ffc107', category: 'accumulation', description: '弹簧效应' },
  { id: 'Test', label: 'Test', color: '#ffab40', category: 'accumulation', description: 'Spring 测试' },
  { id: 'SOS', label: 'SOS', color: '#66bb6a', category: 'accumulation', description: '强势信号' },
  { id: 'LPS', label: 'LPS', color: '#26a69a', category: 'accumulation', description: '最后支撑点' },
  { id: 'BU', label: 'BU', color: '#26a69a', category: 'accumulation', description: '回踩确认' },
  { id: 'JOC', label: 'JOC', color: '#ab47bc', category: 'accumulation', description: '跳跃过河' },
  { id: 'Creek', label: 'Creek', color: '#4db6ac', category: 'accumulation', description: '小溪线' },
  { id: 'Ice', label: 'Ice', color: '#80deea', category: 'accumulation', description: '冰线' },

  // ── 派发阶段 ──
  { id: 'BC', label: 'BC', color: '#ef5350', category: 'distribution', description: '购买高潮' },
  { id: 'UTAD', label: 'UTAD', color: '#ffc107', category: 'distribution', description: '派发后上冲' },
  { id: 'UT', label: 'UT', color: '#ffb74d', category: 'distribution', description: '上冲回落' },
  { id: 'UTA', label: 'UTA', color: '#ffa726', category: 'distribution', description: '上冲回落确认' },
  { id: 'SOW', label: 'SOW', color: '#ff7043', category: 'distribution', description: '弱势信号' },
  { id: 'LPSY', label: 'LPSY', color: '#ff7043', category: 'distribution', description: '最后供应点' },
  { id: 'PSY', label: 'PSY', color: '#8d6e63', category: 'distribution', description: '初始供应' },

  // ── 趋势 ──
  { id: 'Markup', label: 'Markup', color: '#66bb6a', category: 'trend', description: '标升阶段' },
  { id: 'Markdown', label: 'Markdown', color: '#ef5350', category: 'trend', description: '标降阶段' },
  { id: 'SOS_bar', label: 'SOS-bar', color: '#81c784', category: 'trend', description: '强势信号K线' },
  { id: 'SOW_bar', label: 'SOW-bar', color: '#e57373', category: 'trend', description: '弱势信号K线' },
  { id: 'MSOS', label: 'MSOS', color: '#a5d6a7', category: 'trend', description: '均线强势信号' },
  { id: 'MSOW', label: 'MSOW', color: '#ef9a9a', category: 'trend', description: '均线弱势信号' },

  // ── 通用标记 ──
  { id: 'TR', label: 'TR', color: '#90a4ae', category: 'general', description: '交易区间' },
  { id: 'Support', label: 'Support', color: '#4caf50', category: 'general', description: '支撑位' },
  { id: 'Resistance', label: 'Resistance', color: '#f44336', category: 'general', description: '阻力位' },
  { id: 'VolClmx', label: 'VolClmx', color: '#e91e63', category: 'general', description: '成交量高潮' },
  { id: 'VolDry', label: 'VolDry', color: '#9e9e9e', category: 'general', description: '成交量枯竭' },

  // ── 自定义文字标注 ──
  { id: 'custom', label: '✏️ 自定义', color: '#b0bec5', category: 'custom', description: '自定义文字标注' },
];

export interface WyckoffPhaseDef {
  id: string;
  label: string;
  color: string;
  description: string;
}

export const WYCKOFF_PHASES: WyckoffPhaseDef[] = [
  { id: 'A', label: 'Phase A', color: '#ef5350', description: '停止前趋势' },
  { id: 'B', label: 'Phase B', color: '#42a5f5', description: '构建原因' },
  { id: 'C', label: 'Phase C', color: '#ffc107', description: '测试' },
  { id: 'D', label: 'Phase D', color: '#66bb6a', description: '趋势内的强势/弱势' },
  { id: 'E', label: 'Phase E', color: '#ab47bc', description: '离开区间' },
];

/** 按分类筛选事件 */
export function getEventsByCategory(category: WyckoffEventDef['category']): WyckoffEventDef[] {
  return WYCKOFF_EVENTS.filter(e => e.category === category);
}

/** 获取非自定义事件（弹窗选择用） */
export function getSelectableEvents(): WyckoffEventDef[] {
  return WYCKOFF_EVENTS.filter(e => e.category !== 'custom');
}

export function getEventColor(eventId: string): string {
  return WYCKOFF_EVENTS.find(e => e.id === eventId)?.color || '#888';
}

export function getPhaseColor(phaseId: string): string {
  return WYCKOFF_PHASES.find(p => p.id === phaseId)?.color || '#888';
}
