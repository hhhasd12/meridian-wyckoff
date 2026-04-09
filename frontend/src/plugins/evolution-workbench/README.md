#进化工作台插件 (evolution-workbench/) — Step 3

## 做什么
P0 的主战场。完整的标注工作流：选标的/周期 → 画图 → 管理标注 → 查看特征。
做完后 19 条验收标准全部通过。

## 页面布局
```
┌─────────────────────────────────────────────────┐
│ Header: [ETHUSDT] [5m][15m][1h][4h][1d][1w]│
├────┬────────────────────────────┬────────────────┤
│工具│                │  Annotation    │
│ ↗│                            │  Panel         │
│ ╱  │       KLineChart           │  ────────────  │
│ ▱  │       (ChartWidget)        │  Feature       │
│ ─  │                            │  Panel         │
│ │  │                            │  (选中时显示)   │
│ 💬 │                            │                │
│ 🏷 │                            │                │
├────┴────────────────────────────┴────────────────┤
│ Footer: 自动保存 ✓  |  标注: 12 · ETHUSDT · 1d  │
└─────────────────────────────────────────────────┘
```

## 文件清单

### 1. index.ts — 插件注册
```typescript
import { MeridianFrontendPlugin } from '../../core/types';
import { EvolutionPage } from './EvolutionPage';

export const evolutionWorkbenchPlugin: MeridianFrontendPlugin = {
  id: 'evolution-workbench',
  name: '进化工作台',
  icon: '📐',
  version: '0.1.0',
  routes: [{ path: '/evolution', component: EvolutionPage }],
};
```

### 2. EvolutionPage.tsx — 主页面
```tsx
import { useState, useEffect, useCallback } from 'react';
import { ChartWidget } from '../../shared/chart/ChartWidget';
import { DrawingToolbar } from '../../shared/chart/DrawingToolbar';
import { AnnotationPanel } from './panels/AnnotationPanel';
import { FeaturePanel } from './panels/FeaturePanel';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { fetchDrawings } from '../../services/api';
import { setupKeyboard } from '../../utils/keyboard';

export function EvolutionPage() {
  const [tool, setTool] = useState('cursor');
  const { symbol, timeframe, setTimeframe } = useAppStore();
  const { drawings, selectedId, loadDrawings } = useDrawingStore();
  const sel = selectedId ? drawings.get(selectedId) : null;

  // 加载标注
  useEffect(() => {
    fetchDrawings(symbol).then(arr => loadDrawings(arr));
  }, [symbol]);

  // 快捷键
  useEffect(() => {
    constundo = useDrawingStore.temporal.getState().undo;
    const redo = useDrawingStore.temporal.getState().redo;
    const del = () => {
      if (selectedId) {
        useDrawingStore.getState().deleteDrawing(selectedId);
      }
    };
    return setupKeyboard(setTool, undo, redo, del);
  }, [selectedId]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header: 标的+ 周期选择 */}
      <header style={{
        height: 44, background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8
      }}>
        <span style={{ fontWeight: 600 }}>{symbol}</span>
        {['5m', '15m', '1h', '4h', '1d', '1w'].map(tf =>
          <button key={tf} onClick={() => setTimeframe(tf)} style={{
            padding: '4px 8px', borderRadius: 4, border: 'none',
            cursor: 'pointer', fontSize: 12,
            background: tf === timeframe ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)'
          }}>{tf}</button>
        )}
      </header>

      {/* Main: 工具栏 + 图表 + 右侧面板 */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}><DrawingToolbar currentTool={tool} onToolChange={setTool} /><div style={{ flex: 1 }}>
          <ChartWidget currentTool={tool} />
        </div>

        <aside style={{
          width: 280, background: 'var(--bg-secondary)',
          borderLeft: '1px solid var(--border)', overflow: 'auto'
        }}>
          <AnnotationPanel />
          {sel && <FeaturePanel drawing={sel} />}
        </aside>
      </div>

      {/* Footer: 状态栏 */}
      <footer style={{
        height: 24, background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', padding: '0 12px',
        fontSize: 11, color: 'var(--text-muted)'
      }}>
        <span>自动保存 ✓</span>
        <span style={{ marginLeft: 'auto' }}>
          标注: {drawings.size} · {symbol} · {timeframe}
        </span>
      </footer>
    </div>
  );
}
```

### 3. panels/AnnotationPanel.tsx — 标注管理
按时间排序的标注列表。点击跳转到对应K线位置。
```tsx
import { useDrawingStore } from '../../../stores/drawingStore';

const EVENT_COLORS: Record<string, string> = {
  SC: '#ef5350', BC: '#ef5350',
  AR: '#26a69a',
  ST: '#42a5f5',
  Spring: '#ffc107', UTAD: '#ffc107',
  SOS: '#66bb6a', SOW: '#ff7043',
  JOC: '#ab47bc'
};

export function AnnotationPanel() {
  const { drawings, selectedId, selectDrawing } = useDrawingStore();

  // 只显示有事件类型的标注，按时间排序
  const sorted = Array.from(drawings.values())
    .filter(d => d.properties.eventType)
    .sort((a, b) => a.points[0]?.time - b.points[0]?.time);

  return (
    <div style={{ padding: 8 }}>
      <h3 style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 8px' }}>
        📋 标注管理 ({sorted.length})
      </h3>

      {sorted.map(d => (
        <button key={d.id}
          onClick={() => selectDrawing(d.id)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '6px 8px', borderRadius: 4,
            border: 'none', cursor: 'pointer',
            width: '100%', textAlign: 'left', fontSize: 12,
            background: d.id === selectedId ? 'var(--accent-dim)' : 'transparent',
            color: 'var(--text-primary)'
          }}>
          {/*颜色圆点 */}
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: EVENT_COLORS[d.properties.eventType] || '#888'
          }} />
          {/* 事件类型 */}
          <span style={{ fontWeight: 600 }}>{d.properties.eventType}</span>
          {/* 日期 */}
          <span style={{ color: 'var(--text-muted)' }}>
            {new Date(d.points[0]?.time).toLocaleDateString()}
          </span>
          {/* 周期 */}
          <span style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
            {d.properties.timeframe}
          </span>
        </button>
      ))}

      {!sorted.length && (
        <p style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
          暂无标注
        </p>
      )}
    </div>
  );
}
```

### 4. panels/FeaturePanel.tsx — 7维特征展示
选中事件标注时显示，从后端实时获取特征数据。
```tsx
import { useEffect, useState } from 'react';
import { fetchFeatures } from '../../../services/api';

export function FeaturePanel({ drawing }: { drawing: any }) {
  const [feat, setFeat] = useState<any>(null);

  useEffect(() => {
    fetchFeatures(drawing.symbol, drawing.id).then(setFeat);
  }, [drawing.id]);

  const f = feat?.features || {};

  const rows = [
    ['量比', f.volume_ratio ? `${f.volume_ratio}x` : '-'],
    ['下影线', f.wick_ratio ? `${(f.wick_ratio * 100).toFixed(0)}%` : '-'],
    ['实体位置', f.body_position ? `${(f.body_position * 100).toFixed(0)}%` : '-'],
    ['距支撑', f.support_distance ? `${f.support_distance}%` : '-'],
    ['恐慌度', f.effort_result?.toFixed(3) || '-'],
    ['趋势长度', f.trend_length ? `${f.trend_length}根` : '-'],
    ['趋势斜率', f.trend_slope?.toFixed(4) || '-'],
  ];

  return (
    <div style={{ padding: 8, borderTop: '1px solid var(--border)' }}>
      <h3 style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 8px' }}>
        🔬 特征 — {drawing.properties.eventType || '?'}
      </h3>

      <table style={{ width: '100%', fontSize: 11 }}>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label as string}>
              <td style={{ color: 'var(--text-muted)', padding: '3px 0' }}>{label}</td>
              <td style={{ textAlign: 'right' }}>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 后续走势 */}
      {f.subsequent_results && (
        <div style={{ marginTop: 8, fontSize: 10}}>
          {Object.entries(f.subsequent_results).map(([k, v]: any) =><span key={k} style={{
              marginRight: 8,
              color: v > 0 ? '#26a69a' : v < 0 ? '#ef5350' : '#888'
            }}>
              {k}: {v > 0 ? '+' : ''}{v}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
```

### 5. utils/keyboard.ts — 快捷键系统
```typescript
export function setupKeyboard(
  setTool: (t: string) => void,
  undo: () => void,
  redo: () => void,
  del: () => void
) {
  const toolMap: Record<string, string> = {
    '1': 'cursor',
    '2': 'trend_line',
    '3': 'parallel_channel',
    '4': 'horizontal_line',
    '5': 'vertical_line',
    '6': 'callout',
    '7': 'phase_marker',
  };

  const handler = (e: KeyboardEvent) => {
    // 如果焦点在输入框内，不拦截
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

    // 数字键切工具
    if (toolMap[e.key]) {
      setTool(toolMap[e.key]);
      return;
    }

    // Esc 回光标
    if (e.key === 'Escape') setTool('cursor');

    // Delete 删除选中标注
    if (e.key === 'Delete') del();

    // Ctrl+Z 撤销
    if (e.ctrlKey && e.key === 'z') {
      e.preventDefault();
      undo();
    }

    // Ctrl+Y 重做
    if (e.ctrlKey && e.key === 'y') {
      e.preventDefault();
      redo();
    }
  };

  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
```

## 画完标注后的数据流
```
用户在图表上画完→ KLineChart 触发 onDrawEnd回调
  → overlayToDrawing() 转换为后端格式
  → drawingStore.addDrawing() 更新本地状态
  → debounce 1秒后POST /api/annotation/drawings/{symbol}
  → 后端保存到 JSON
  → 后端发布annotation.created 事件
```

## 验收检查点
- [ ] 选标的和周期 → K线图更新
- [ ] 7种画图工具都能用
- [ ] 画完后刷新 → 标注仍在
- [ ] 右侧面板显示标注列表
- [ ] 点击标注 → 图表跳转
- [ ] 选中事件标注 → 显示7维特征
- [ ] 日线标注 → 切4H →仍可见
- [ ] 数字键切工具 / Esc回光标 / Del删除 / Ctrl+Z撤销---

## P1: 威科夫语义层

### 设计原则
- 所有威科夫概念（事件类型 SC/AR/ST、阶段 A/B/C/D/E、颜色映射）在**此插件内**定义
- 通过 `shared/chart` 的 `ChartExtension` 接口与图表通信
- 图表不知道威科夫是什么 — 插件赋予图表威科夫语义
- 以后加新事件类型 → 改`config/wyckoffEvents.ts` 的数组，加一行
- 以后换颜色方案 → 改同一个文件
- 以后做别的方法论 → 新建一个插件，用同样的 ChartExtension 接口

### 新建文件夹
| 文件夹 | 说明 |
|--------|------|
| components/ | 弹窗和编辑器组件 |
| config/ | 威科夫事件和阶段定义 |

### 新建文件清单
| 文件 | 说明 |
|------|------|
| config/wyckoffEvents.ts | 事件类型 + 阶段定义（数据源） |
| components/EventTypePopup.tsx | 画完气泡后弹出的事件选择窗 |
| components/PhaseSelectPopup.tsx | 画完阶段标记后弹出的阶段选择窗 |
| components/PropertyEditor.tsx | 选中标注后的属性编辑面板 |

### 修改文件清单
| 文件 | 改动 |
|------|------|
| EvolutionPage.tsx | 构建 ChartExtension + 管理弹窗状态 + 画完保存管线 |
| panels/AnnotationPanel.tsx | 集成 PropertyEditor |

### 施工顺序
1. config/wyckoffEvents.ts →2. EventTypePopup → 3. PhaseSelectPopup → 4. PropertyEditor → 5. EvolutionPage.tsx 修改 → 6. AnnotationPanel.tsx 修改

---

### 新建: config/wyckoffEvents.ts

```typescript
/**
 * 威科夫事件类型和阶段定义
 * 所有威科夫语义的唯一数据源
 * 加新事件类型 → 在WYCKOFF_EVENTS 数组加一行
 */

export interface WyckoffEventDef {
  id: string;
  label: string;
  color: string;
  category: 'accumulation' | 'distribution' | 'both';
  description: string;
}

export const WYCKOFF_EVENTS: WyckoffEventDef[] = [
  //── 通用 ──
  { id: 'PS',label: 'PS',     color: '#78909c', category: 'both',description: '初始支撑/供应' },
  { id: 'AR',     label: 'AR',     color: '#26a69a', category: 'both',         description: '自动反弹/回落' },
  { id: 'ST',     label: 'ST',     color: '#42a5f5', category: 'both',         description: '二次测试' },
  // ── 吸筹 ──
  { id: 'SC',     label: 'SC',     color: '#ef5350', category: 'accumulation', description: '抛售高潮' },
  { id: 'Spring', label: 'Spring', color: '#ffc107', category: 'accumulation', description: '弹簧效应' },
  { id: 'Test',   label: 'Test',   color: '#ffab40', category: 'accumulation', description: 'Spring 测试' },
  { id: 'SOS',    label: 'SOS',    color: '#66bb6a', category: 'accumulation', description: '强势信号' },
  { id: 'LPS',    label: 'LPS',    color: '#26a69a', category: 'accumulation', description: '最后支撑点' },
  { id: 'BU',     label: 'BU',     color: '#26a69a', category: 'accumulation', description: '回踩确认' },
  { id: 'JOC',    label: 'JOC',    color: '#ab47bc', category: 'accumulation', description: '跳跃过河' },
  // ── 派发 ──
  { id: 'BC',     label: 'BC',     color: '#ef5350', category: 'distribution', description: '购买高潮' },
  { id: 'UTAD',   label: 'UTAD',   color: '#ffc107', category: 'distribution', description: '派发后上冲' },
  { id: 'SOW',    label: 'SOW',    color: '#ff7043', category: 'distribution', description: '弱势信号' },
  { id: 'LPSY',   label: 'LPSY',   color: '#ff7043', category: 'distribution', description: '最后供应点' },
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

/** 根据事件 ID 获取颜色 */
export function getEventColor(eventId: string): string {
  return WYCKOFF_EVENTS.find(e => e.id === eventId)?.color || '#888';
}

/** 根据阶段 ID 获取颜色 */
export function getPhaseColor(phaseId: string): string {
  return WYCKOFF_PHASES.find(p => p.id === phaseId)?.color || '#888';
}
```

---

### 新建: components/EventTypePopup.tsx

```tsx
/**
 * 事件类型选择弹窗
 * 用户画完 callout overlay 后弹出，选择事件类型（SC/AR/ST/Spring...）
 * 选择后自动设置颜色和文字，保存到后端
 */
import { WYCKOFF_EVENTS, WyckoffEventDef } from '../config/wyckoffEvents';

interface Props {
  /**弹窗定位：画完时鼠标的像素坐标 */
  position: { x: number; y: number };
  /** 选择事件类型后的回调 */
  onSelect: (event: WyckoffEventDef) => void;
  /** 取消/关闭弹窗 */
  onCancel: () => void;
}

export function EventTypePopup({ position, onSelect, onCancel }: Props) {
  // 边界保护：弹窗不超出屏幕
  const left = Math.min(position.x, window.innerWidth - 280);
  const top = Math.min(position.y + 10, window.innerHeight - 220);

  return (
    <>
      {/* 背景遮罩：点击关闭 */}
      <div
        onClick={onCancel}
        style={{
          position: 'fixed', inset: 0, zIndex: 999,
          background: 'transparent',}}
      />
      {/* 弹窗本体 */}
      <div style={{
        position: 'fixed', left, top,
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 8,
        zIndex: 1000,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        minWidth: 240,
      }}>
        <div style={{
          fontSize: 11, color: 'var(--text-muted)',
          marginBottom: 6, paddingLeft: 4,
        }}>
          选择事件类型
        </div>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 4,
        }}>
          {WYCKOFF_EVENTS.map(evt => (
            <button
              key={evt.id}
              onClick={() => onSelect(evt)}
              title={evt.description}
              style={{
                padding: '5px 0',
                borderRadius: 4,
                border: `1px solid ${evt.color}40`,
                background: `${evt.color}15`,
                color: evt.color,
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'monospace',
              }}
            >
              {evt.label}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
```

---

### 新建: components/PhaseSelectPopup.tsx

```tsx
/**
 * 阶段选择弹窗
 * 用户画完 phaseMarker overlay 后弹出，选择阶段（A/B/C/D/E）
 */
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
    <><div onClick={onCancel} style={{
        position: 'fixed', inset: 0, zIndex: 999, background: 'transparent',
      }} />
      <div style={{
        position: 'fixed', left, top,
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 8,
        zIndex: 1000,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',}}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, paddingLeft: 4 }}>
          选择阶段
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {WYCKOFF_PHASES.map(phase => (
            <button
              key={phase.id}
              onClick={() => onSelect(phase)}
              title={phase.description}
              style={{
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
              }}
            ><span>{phase.label}</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                {phase.description}
              </span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
```

---

### 新建: components/PropertyEditor.tsx

```tsx
/**
 * 标注属性编辑器
 * 在AnnotationPanel 底部，选中标注时展开
 * 可修改：事件类型、文字标签、颜色
 */
import { WYCKOFF_EVENTS } from '../config/wyckoffEvents';
import { useDrawingStore } from '../../../stores/drawingStore';
import { updateDrawingApi } from '../../../services/api';
import { useAppStore } from '../../../stores/appStore';

interface Props {
  drawing: any;
}

export function PropertyEditor({ drawing }: Props) {
  const { updateDrawing } = useDrawingStore();
  const { symbol } = useAppStore();

  /** 修改并同步到 store +后端 */
  const applyUpdate = (propUpdates: Record<string, any>) => {
    const updates = {
      properties: { ...drawing.properties, ...propUpdates },
    };
    updateDrawing(drawing.id, updates);
    updateDrawingApi(symbol, drawing.id, updates);
  };

  return (
    <div style={{
      padding: 10,
      borderTop: '1px solid var(--border)',
      fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 8, fontSize: 11 }}>
        ✏️ 编辑属性
      </div>

      {/* 事件类型快速切换 */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 4 }}>事件类型</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
          {WYCKOFF_EVENTS.map(evt => (
            <button
              key={evt.id}
              onClick={() => applyUpdate({
                eventType: evt.id,
                text: evt.label,
                color: evt.color,
              })}
              title={evt.description}
              style={{
                padding: '2px 6px',
                borderRadius: 3,
                border: drawing.properties.eventType === evt.id
                  ? `2px solid ${evt.color}`
                  : `1px solid ${evt.color}30`,
                background: drawing.properties.eventType === evt.id
                  ? `${evt.color}30`
                  : 'transparent',
                color: evt.color,
                cursor: 'pointer',
                fontSize: 10,
                fontWeight: 600,
                fontFamily: 'monospace',
              }}
            >
              {evt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 文字标签输入 */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 4 }}>文字标签</div>
        <input
          type="text"
          value={drawing.properties.text || ''}
          onChange={(e) => applyUpdate({ text: e.target.value })}
          placeholder="Ice / Creek / Support..."
          style={{
            width: '100%',
            padding: '4px 8px',
            borderRadius: 4,
            border: '1px solid var(--border)',
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            fontSize: 12,
            outline: 'none',
          }}
        />
      </div>

      {/* 颜色选择 */}
      <div>
        <div style={{ color: 'var(--text-muted)', fontSize: 10, marginBottom: 4 }}>颜色</div>
        <div style={{ display: 'flex', gap: 4 }}>
          {['#ef5350', '#26a69a', '#42a5f5', '#ffc107', '#66bb6a', '#ff7043', '#ab47bc', '#78909c'].map(c => (
            <button
              key={c}
              onClick={() => applyUpdate({ color: c })}
              style={{
                width: 20, height: 20,
                borderRadius: '50%',
                border: drawing.properties.color === c
                  ? '2px solid #fff'
                  : '2px solid transparent',
                background: c,
                cursor: 'pointer',
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
```

---

### 修改: EvolutionPage.tsx

**这是 P1 最核心的修改 — 画完保存管线在这里接通。**

改动要点：
1. 导入 ChartExtension 类型+弹窗组件 + overlayToDrawing + API
2. 新增 popup 状态管理
3. 用 useMemo 构建 chartExtension 对象
4. 传chartExtension 给 ChartWidget
5. 渲染弹窗层
6. 画完自动切回 cursor模式

```tsx
// ===== 完整代码骨架 =====
import { useState, useEffect, useMemo } from 'react';
import { ChartWidget } from '../../shared/chart/ChartWidget';
import { DrawingToolbar } from '../../shared/chart/DrawingToolbar';
import { AnnotationPanel } from './panels/AnnotationPanel';
import { FeaturePanel } from './panels/FeaturePanel';
import { EventTypePopup } from './components/EventTypePopup';
import { PhaseSelectPopup } from './components/PhaseSelectPopup';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { fetchDrawings, saveDrawing, updateDrawingApi } from '../../services/api';
import { setupKeyboard } from '../../utils/keyboard';
import { overlayToDrawing } from '../../shared/chart/chartUtils';
import { ChartExtension, OverlayEvent } from '../../shared/chart/types';
import { WyckoffEventDef, WyckoffPhaseDef } from './config/wyckoffEvents';

/**弹窗状态类型 */
type PopupState =
  | null
  | { type: 'eventType'; overlay: OverlayEvent; position: { x: number; y: number } }
  | { type: 'phase';overlay: OverlayEvent; position: { x: number; y: number } };

export function EvolutionPage() {
  const [tool, setTool] = useState('cursor');
  const [popup, setPopup] = useState<PopupState>(null);
  const { symbol, timeframe, setTimeframe } = useAppStore();
  const { drawings, selectedId, addDrawing, selectDrawing, loadDrawings } = useDrawingStore();
  const sel = selectedId ? drawings.get(selectedId) : null;

  // 加载已有标注
  useEffect(() => {
    fetchDrawings(symbol).then(arr => {
      if (Array.isArray(arr)) loadDrawings(arr);
    });
  }, [symbol]);

  // 快捷键
  useEffect(() => {
    constundo = useDrawingStore.temporal.getState().undo;
    const redo = useDrawingStore.temporal.getState().redo;
    const del = () => {
      if (selectedId) useDrawingStore.getState().deleteDrawing(selectedId);
    };
    return setupKeyboard(setTool, undo, redo, del);
  }, [selectedId]);

  // ★ 构建图表扩展 — 画完保存管线的核心
  const chartExtension = useMemo<ChartExtension>(() => ({
    magnetMode: 'strong_magnet',

    onDrawComplete: (event: OverlayEvent, bindPoint: { x: number; y: number }) => {
      if (event.name === 'callout') {
        // 气泡标记→弹出事件类型选择
        setPopup({ type: 'eventType', overlay: event, position: bindPoint });
      } else if (event.name === 'phaseMarker') {
        // 阶段标记 → 弹出阶段选择
        setPopup({ type: 'phase', overlay: event, position: bindPoint });
      } else {
        // 其他类型（趋势线、通道等）→ 直接保存
        const drawing = overlayToDrawing(event, symbol, timeframe);
        addDrawing(drawing);
        saveDrawing(symbol, drawing);
      }
      setTool('cursor'); // 画完切回选择模式
    },

    onOverlayClick: (event: OverlayEvent) => {
      selectDrawing(event.overlayId);
    },

    onOverlayMoveEnd: (event: OverlayEvent) => {
      //拖动结束 → 自动保存新位置
      const drawing = overlayToDrawing(event, symbol, timeframe);
      updateDrawingApi(symbol, event.overlayId, {
        points: drawing.points,
        updated_at: new Date().toISOString(),
      });
    },
  }), [symbol, timeframe, addDrawing, selectDrawing]);

  //事件类型选择回调
  const handleEventSelect = (eventDef: WyckoffEventDef) => {
    if (!popup || popup.type !== 'eventType') return;
    const drawing = overlayToDrawing(popup.overlay, symbol, timeframe);
    drawing.properties.eventType = eventDef.id;
    drawing.properties.text = eventDef.label;
    drawing.properties.color = eventDef.color;
    addDrawing(drawing);
    saveDrawing(symbol, drawing);
    setPopup(null);
  };

  // 阶段选择回调
  const handlePhaseSelect = (phaseDef: WyckoffPhaseDef) => {
    if (!popup || popup.type !== 'phase') return;
    const drawing = overlayToDrawing(popup.overlay, symbol, timeframe);
    drawing.properties.phase = phaseDef.id;
    drawing.properties.text = phaseDef.label;
    drawing.properties.color = phaseDef.color;
    addDrawing(drawing);
    saveDrawing(symbol, drawing);
    setPopup(null);
  };

  // 取消弹窗
  const handlePopupCancel = () => {
    setPopup(null);// 注意：取消时overlay仍留在图表上，下次 drawings 变化时会被清理// （因为第3个useEffect 会 removeOverlay + 从 store 重建）
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-primary)' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 12px', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{symbol}</span>
        {['5m', '15m', '1h', '4h', '1d', '1w'].map(tf => (
          <button key={tf} onClick={() => setTimeframe(tf)} style={{
            padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 12,
            background: tf === timeframe ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)',
          }}>{tf}</button>
        ))}
      </div>

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <DrawingToolbar currentTool={tool} onToolChange={setTool} />
        <ChartWidget currentTool={tool} chartExtension={chartExtension} />
        <div style={{
          width: 260, borderLeft: '1px solid var(--border)',
          overflow: 'auto', background: 'var(--bg-secondary)',
        }}>
          <AnnotationPanel />
          {sel && <FeaturePanel drawing={sel} />}
        </div>
      </div>

      {/* 弹窗层 */}
      {popup?.type === 'eventType' && (
        <EventTypePopup
          position={popup.position}
          onSelect={handleEventSelect}
          onCancel={handlePopupCancel}
        />
      )}
      {popup?.type === 'phase' && (
        <PhaseSelectPopup
          position={popup.position}
          onSelect={handlePhaseSelect}
          onCancel={handlePopupCancel}
        />
      )}

      {/* Footer */}
      <div style={{
        padding: '4px 12px', borderTop: '1px solid var(--border)',
        fontSize: 11, color: 'var(--text-muted)',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span>标注: {drawings.size} · {symbol} · {timeframe}</span></div>
    </div>
  );
}
```

---

### 修改: panels/AnnotationPanel.tsx

**改动要点：** 选中标注时，在列表下方展开PropertyEditor

```tsx
// 在文件顶部新增导入
import { PropertyEditor } from '../components/PropertyEditor';

// 在组件末尾、关闭 </div> 之前，加入：
// （在 "暂无标注" 的div 之后）

export function AnnotationPanel() {
  const { drawings, selectedId, selectDrawing } = useDrawingStore();
  const sorted = /* ... 与 P0 相同 ... */;
  const selectedDrawing = selectedId ? drawings.get(selectedId) : null;

  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
        📋 标注管理 ({sorted.length})
      </div>

      {/* 标注列表 — 与 P0 相同 */}
      {sorted.map(d => (
        /* ... P0 代码不变 ... */
      ))}
      {!sorted.length && <div style={{ /* ... */ }}>暂无标注</div>}

      {/* ★ P1 新增：选中时展开属性编辑器 */}
      {selectedDrawing && <PropertyEditor drawing={selectedDrawing} />}
    </div>
  );
}
```

---

### chartUtils.ts 小改动

`overlayToDrawing` 函数需要兼容 `OverlayEvent` 类型（P1 的 ChartExtension 传过来的）：

```typescript
// overlayToDrawing 的第一个参数可能是：
// - KLineChart 原生overlay 对象（有 .id）
// - OverlayEvent 对象（有 .overlayId）
// 兼容处理：
export function overlayToDrawing(o: any, symbol: string, tf: string) {
  return {
    id: o.id || o.overlayId || crypto.randomUUID(),  // ← 加o.overlayId
    // ... 其余不变 ...
  };
}
```

---

### 施工验收标准（P1 威科夫语义层）

1. 画完 callout → 弹出事件选择窗 → 选SC → 气泡显示 "SC" 红色 → 保存到后端
2. 画完 phaseMarker → 弹出阶段选择 → 选 Phase C → 显示黄色垂直线 + "Phase C" 标签 → 保存
3. 画趋势线/通道 → 直接保存，无弹窗
4. 点击弹窗外部 → 弹窗关闭
5. 选中已有标注 → AnnotationPanel 底部展开属性编辑器
6. 在属性编辑器中改事件类型 → 图表上的标注同步更新颜色和文字
7. 在属性编辑器中改文字 → 图表上同步
8. 磁吸生效：画线时自动吸附 K线 OHLC 价格
9. 画完任何工具后自动切回 cursor 模式
10. 刷新页面后标注仍在（持久化验证）