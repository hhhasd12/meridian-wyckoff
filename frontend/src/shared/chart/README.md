# 图表核心 (shared/chart/) — Step 2

## 做什么
封装 KLineChart，注册自定义 Overlay（平行通道/事件气泡/阶段标记），实现 Drawing ↔ Overlay 双向映射。
做完后能在图表上画线、画通道、标事件，切换周期标注跟随。

## 为什么用 KLineChart 而不是 Lightweight Charts
- KLineChart 内置15 种画图工具 + 自定义 overlay API
- LWC 没有画图工具，从零实现需5000 行交互代码
- KLineChart 内置磁吸、命中检测、拖拽，省60% 工程量
- 文档：https://klinecharts.com/

## 文件清单（按施工顺序）

### 1. overlays/parallelChannel.ts — 平行通道
3点绘制：点1+点2 定第一条线，点3 定通道宽度。半透明填充。
```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'parallelChannel',
  totalStep: 3,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    const figs: any[] = [];
    const color = overlay.extendData?.color || '#2196F3';

    // 第一条线（点1→点2）
    if (coordinates.length >= 2) {
      figs.push({
        type: 'line',
        attrs: { coordinates: [coordinates[0], coordinates[1]] },
        styles: { style: 'solid', color, size: 1.5 }
      });
    }

    // 第二条线（平行）+ 填充
    if (coordinates.length >= 3) {
      const oY = coordinates[2].y - coordinates[0].y;
      figs.push({
        type: 'line',
        attrs: { coordinates: [
          { x: coordinates[0].x, y: coordinates[0].y + oY },
          { x: coordinates[1].x, y: coordinates[1].y + oY }
        ]},
        styles: { style: 'solid', color, size: 1.5 }
      });
      // 半透明填充
      figs.push({
        type: 'polygon',
        attrs: { coordinates: [
          coordinates[0], coordinates[1],
          { x: coordinates[1].x, y: coordinates[1].y + oY },
          { x: coordinates[0].x, y: coordinates[0].y + oY }
        ]},
        styles: { style: 'fill', color: color + '15' }
      });
    }
    return figs;
  },
  performEventPressedMove: ({ currentStep, points, performPoint }) => {
    // 第三个点只允许垂直移动（保持平行）
    if (currentStep === 3) performPoint.timestamp = points[0].timestamp;
  }
});
```

### 2. overlays/callout.ts — 事件气泡
单点标记：彩色标签+ 虚线指向K线。用于标注SC/AR/ST/Spring 等威科夫事件。
```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'callout',
  totalStep: 2,
  needDefaultPointFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    if (!coordinates.length) return [];
    const p = coordinates[0];
    const text = overlay.extendData?.text || 'SC';
    const color = overlay.extendData?.color || '#FF5252';
    return [
      // 文字标签
      {
        type: 'rectText',
        attrs: { x: p.x, y: p.y - 25, text, align: 'center', baseline: 'middle' },
        styles: {
          style: 'fill', color: '#FFF', size: 11, family: 'monospace',
          backgroundColor: color, borderRadius: 3,
          paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2
        }
      },
      // 虚线连接
      {
        type: 'line',
        attrs: { coordinates: [{ x: p.x, y: p.y - 14 }, p] },
        styles: { style: 'dashed', color, size: 1, dashedValue: [3, 3] }
      }
    ];
  }
});
```

### 3. overlays/phaseMarker.ts — 阶段标记
单点标记：边框文字标签。用于标注 Phase A/B/C/D/E。
```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'phaseMarker',
  totalStep: 2,
  needDefaultPointFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    if (!coordinates.length) return [];
    const p = coordinates[0];
    const text = overlay.extendData?.text || 'Phase A';
    const color = overlay.extendData?.color || '#FFC107';
    return [{
      type: 'rectText',
      attrs: { x: p.x, y: p.y, text, align: 'center', baseline: 'top' },
      styles: {
        style: 'stroke', color, size: 10,
        borderColor: color, borderSize: 1, borderRadius: 2,
        paddingLeft: 6, paddingRight: 6, paddingTop: 2, paddingBottom: 2
      }
    }];
  }
});
```

### 4. chartUtils.ts — Drawing↔ Overlay 双向映射
后端存的是 Drawing（数据坐标），KLineChart 用的是 Overlay（像素坐标）。这个文件做双向转换。
```typescript
// Drawing.type → KLineChart overlay name
const TYPE_MAP: Record<string, string> = {
  trend_line: 'segment',
  parallel_channel: 'parallelChannel',
  horizontal_line: 'horizontalStraightLine',
  vertical_line: 'verticalStraightLine',
  rectangle: 'rect',
  callout: 'callout',
  phase_marker: 'phaseMarker'
};

// 反向映射
const REV: Record<string, string> = {};
Object.entries(TYPE_MAP).forEach(([k, v]) => REV[v] = k);

/**
 * 后端 Drawing → KLineChart Overlay
 * 用于从后端加载标注后渲染到图表
 */
export function drawingToOverlay(d: any) {
  return {
    id: d.id,
    name: TYPE_MAP[d.type] || d.type,
    points: d.points.map((p: any) => ({ timestamp: p.time, value: p.price })),
    extendData: {
      color: d.properties.color,
      text: d.properties.text || d.properties.eventType,
      eventType: d.properties.eventType,
      phase: d.properties.phase
    },
    lock: false
  };
}

/**
 * KLineChart Overlay → 后端 Drawing
 * 用于画完后发送到后端保存
 */
export function overlayToDrawing(o: any, symbol: string, tf: string) {
  return {
    id: o.id || crypto.randomUUID(),
    symbol,
    type: REV[o.name] || o.name,
    points: (o.points || []).map((p: any) => ({ time: p.timestamp, price: p.value })),
    properties: {
      color: o.extendData?.color,
      text: o.extendData?.text,
      eventType: o.extendData?.eventType,
      phase: o.extendData?.phase,
      timeframe: tf
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };
}

/**
 * 多周期可见性判断
 * 大周期标注在小周期上仍然可见（Top-down 分析）
 * 例：日线标注在 4H 图上可见，反过来不行
 */
const TF_HIER = ['5m', '15m', '1h', '4h', '1d', '1w'];

export function shouldShowDrawing(drawingTf: string, currentTf: string) {
  return TF_HIER.indexOf(drawingTf) >= TF_HIER.indexOf(currentTf);
}
```

### 5. ChartWidget.tsx — KLineChart 封装
核心图表组件。负责：初始化图表、加载K线、渲染标注、响应工具切换。
```tsx
import { useRef, useEffect } from 'react';
import { init, dispose, Chart } from 'klinecharts';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { fetchCandles, decodeCandlesFromBinary } from '../../services/api';
import { drawingToOverlay, shouldShowDrawing } from './chartUtils';

// 注册自定义 Overlay（import 即执行）
import './overlays/parallelChannel';
import './overlays/callout';
import './overlays/phaseMarker';

export function ChartWidget({ currentTool}: { currentTool?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<Chart | null>(null);
  const { symbol, timeframe } = useAppStore();
  const { drawings } = useDrawingStore();

  // 初始化图表（只执行一次）
  useEffect(() => {
    if (!ref.current) return;
    chart.current = init(ref.current, {
      styles: {
        grid: {
          show: true,
          horizontal: { color: '#1e222d' },
          vertical: { color: '#1e222d' }
        },
        candle: {
          type: 'candle_solid',
          bar: {
            upColor: '#26a69a',
            downColor: '#ef5350',
            noChangeColor: '#888'
          }
        }
      }
    });
    // 底部成交量指标
    chart.current.createIndicator('VOL', false, { id: 'vol' });
    return () => { if (ref.current) dispose(ref.current); };
  }, []);

  // 加载K线数据（symbol或timeframe变化时）
  useEffect(() => {
    if (!chart.current) return;
    (async () => {
      const raw = await fetchCandles(symbol, timeframe);
      chart.current!.applyNewData(decodeCandlesFromBinary(raw));
    })();
  }, [symbol, timeframe]);

  // 渲染标注（drawings或timeframe变化时）
  useEffect(() => {
    if (!chart.current) return;
    chart.current.removeOverlay();
    drawings.forEach(d => {
      if (shouldShowDrawing(d.properties.timeframe || timeframe, timeframe)) {
        chart.current!.createOverlay(drawingToOverlay(d));
      }
    });
  }, [drawings, timeframe]);

  // 工具切换（激活画图模式）
  useEffect(() => {
    if (!chart.current || !currentTool || currentTool === 'cursor') return;
    const nameMap: Record<string, string> = {
      trend_line: 'segment',
      parallel_channel: 'parallelChannel',
      horizontal_line: 'horizontalStraightLine',
      vertical_line: 'verticalStraightLine',
      callout: 'callout',
      phase_marker: 'phaseMarker'
    };
    const name = nameMap[currentTool];
    if (name) chart.current.createOverlay({ name });
  }, [currentTool]);

  return<div ref={ref} style={{ width: '100%', height: '100%', background: '#131722' }} />;
}
```

### 6. DrawingToolbar.tsx — 画图工具栏
垂直工具栏，7个工具按钮。
```tsx
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
```

## KLineChart 关键 API 速查
| 方法 | 用途 |
|------|------|
| init(dom, options) | 初始化图表 |
| dispose(dom) | 销毁图表 |
| applyNewData(data) | 加载K线数据（替换） |
| applyMoreData(data) | 追加历史数据 |
| updateData(bar) | 更新最新一根K线 |
| createOverlay(config) | 创建标注/画图 |
| removeOverlay(id?) | 删除标注（无参=全删） |
| createIndicator(name) | 创建技术指标 |
| registerOverlay(config) | 注册自定义 Overlay 类型 |

## KLineChart 磁吸模式
```typescript
// 在 init 时配置
chart = init(dom, {
  crosshair: {
    // strong_magnet: 强磁吸，吸附到OHLC
    // weak_magnet: 弱磁吸
    // normal: 不吸附
    snap: 'strong_magnet'
  }
});
```

## 施工注意
- Overlay 的 import 必须在 ChartWidget 之前执行（import 即注册）
- 只存数据坐标（timestamp + price），不存像素坐标
- KLineChart 的 timestamp 是毫秒级 Unix 时间戳
- 画完后要触发 overlayToDrawing 转换 → 存到drawingStore → POST 后端
- 自动保存用debounce 1秒---

## P1: 图表扩展接口（Chart Extension Interface）

### 设计原则
- ChartWidget 是通用 K 线图表组件，**不包含任何威科夫概念**
- 插件通过 `ChartExtension` 接口注入语义行为（画完弹窗、选中编辑、磁吸模式）
- ChartWidget 只负责：渲染 K 线 + 渲染 overlay + 触发回调
- "画完之后做什么" 由插件决定，图表不关心

### 新建文件清单
| 文件 | 说明 |
|------|------|
| types.ts | ChartExtension 接口 +OverlayEvent 类型 |

### 修改文件清单
| 文件 | 改动 |
|------|------|
| ChartWidget.tsx | 新增 chartExtension prop，接入 onDrawEnd/onClick/onPressedMoveEnd 回调，应用磁吸模式 |
| overlays/phaseMarker.ts | 加入垂直虚线（从图表顶到底） |

---

### 新建: types.ts

```typescript
/**
 * 图表扩展接口
 * 插件通过此接口向 ChartWidget 注入行为，ChartWidget 本身不含业务逻辑
 */

/** overlay 事件数据（画完/选中/移动时传递给插件） */
export interface OverlayEvent {
  overlayId: string;
  name: string;
  points: { timestamp: number; value: number }[];
  extendData?: Record<string, any>;
}

/** 插件注入的图表扩展配置 */
export interface ChartExtension {
  /**
   * 用户画完一个 overlay 后触发
   * @param event - overlay 数据
   * @param bindPoint - 画完时鼠标的像素坐标（用于定位弹窗）
   */
  onDrawComplete?: (event: OverlayEvent, bindPoint: { x: number; y: number }) => void;

  /**
   * 用户点击已有 overlay 时触发（用于选中/编辑）
   */
  onOverlayClick?: (event: OverlayEvent) => void;

  /**
   * 用户拖动overlay 结束后触发（用于自动保存位置变更）
   */
  onOverlayMoveEnd?: (event: OverlayEvent) => void;

  /**
   *磁吸模式
   * - 'normal': 无磁吸
   * - 'weak_magnet': 弱磁吸
   * - 'strong_magnet': 强磁吸，吸附到最近的 OHLC 价格
   */
  magnetMode?: 'normal' | 'weak_magnet' | 'strong_magnet';
}
```

---

### 修改: ChartWidget.tsx

**改动要点：**
1. 新增 prop `chartExtension?: ChartExtension`
2. 第4 个 useEffect（工具激活）重写：创建 overlay 时注入 KLineChart 回调
3. 删除组件内重复的 `nameMap`，复用 `chartUtils.ts` 的 `TYPE_MAP`
4. 第 2 个 useEffect（数据加载）加`response.ok` 检查

```tsx
// ===== 完整代码骨架 =====
import { useRef, useEffect } from 'react';
import { init, dispose, Chart } from 'klinecharts';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { useDataWorker } from '../../workers/useDataWorker';
import { drawingToOverlay, shouldShowDrawing, TYPE_MAP } from './chartUtils';
import { ChartExtension, OverlayEvent } from './types';
import './overlays/parallelChannel';
import './overlays/callout';
import './overlays/phaseMarker';

export function ChartWidget({
  currentTool,
  chartExtension,
}: {
  currentTool?: string;
  chartExtension?: ChartExtension;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<Chart | null>(null);
  const { symbol, timeframe } = useAppStore();
  const { drawings } = useDrawingStore();
  const { decodeCandles } = useDataWorker();

  // ① 初始化 — 与 P0 相同，不变
  useEffect(() => {
    if (!ref.current) return;
    chart.current = init(ref.current, {
      styles: {
        grid: {
          show: true,
          horizontal: { color: '#1e222d' },
          vertical: { color: '#1e222d' },},
        candle: {
          type: 'candle_solid',
          bar: { upColor: '#26a69a', downColor: '#ef5350', noChangeColor: '#888' },
        },
      },
    });
    chart.current.createIndicator('VOL', false, { id: 'vol' });
    return () => { if (ref.current) dispose(ref.current); };
  }, []);

  // ② 数据加载 — 加response.ok 检查
  useEffect(() => {
    if (!chart.current) return;
    (async () => {
      const response = await fetch(`/api/datasource/candles/${symbol}/${timeframe}`);
      if (!response.ok) {
        console.error(`加载K线失败: ${response.status} ${response.statusText}`);
        return;
      }
      const buffer = await response.arrayBuffer();
      const candles = await decodeCandles(buffer);
      chart.current!.applyNewData(candles);
    })();
  }, [symbol, timeframe, decodeCandles]);

  // ③ overlay 同步 — 与 P0 相同，不变
  useEffect(() => {
    if (!chart.current) return;
    chart.current.removeOverlay();
    drawings.forEach((d) => {
      if (shouldShowDrawing(d.properties.timeframe || timeframe, timeframe)) {
        chart.current!.createOverlay(drawingToOverlay(d));
      }
    });
  }, [drawings, timeframe]);

  // ④ 工具激活 — 重写：接入扩展接口
  useEffect(() => {
    if (!chart.current || !currentTool || currentTool === 'cursor') return;

    const overlayName = TYPE_MAP[currentTool];
    if (!overlayName) return;

    //辅助函数：从KLineChart 回调参数提取 OverlayEvent
    const toOverlayEvent = (kEvent: any): OverlayEvent => ({
      overlayId: kEvent.overlay?.id || '',
      name: kEvent.overlay?.name || '',
      points: (kEvent.overlay?.points || []).map((p: any) => ({
        timestamp: p.timestamp,
        value: p.value,
      })),
      extendData: kEvent.overlay?.extendData,
    });

    chart.current.createOverlay({
      name: overlayName,
      mode: chartExtension?.magnetMode || 'normal',

      // 画完回调
      onDrawEnd: (kEvent: any) => {
        chartExtension?.onDrawComplete?.(
          toOverlayEvent(kEvent),
          { x: kEvent.bindPoint?.x ?? 0, y: kEvent.bindPoint?.y ?? 0 }
        );
        return true; // true = 保留 overlay 在图表上
      },

      // 点击回调
      onClick: (kEvent: any) => {
        chartExtension?.onOverlayClick?.(toOverlayEvent(kEvent));},

      // 拖动结束回调
      onPressedMoveEnd: (kEvent: any) => {
        chartExtension?.onOverlayMoveEnd?.(toOverlayEvent(kEvent));
      },
    });
  }, [currentTool, chartExtension]);

  return<div ref={ref} style={{ flex: 1 }} />;
}
```

**注意：** `TYPE_MAP` 需要从 `chartUtils.ts` 导出。当前 chartUtils.ts 中TYPE_MAP 是模块内部变量，需要加 `export`：

```typescript
// chartUtils.ts 第1行改为：
export const TYPE_MAP: Record<string, string> = {
```

---

### 修改: overlays/phaseMarker.ts

**改动：** 加入从图表顶部到底部的垂直虚线

```typescript
import { registerOverlay } from 'klinecharts';

registerOverlay({
  name: 'phaseMarker',
  totalStep: 2,
  needDefaultPointFigure: true,
  createPointFigures: ({ coordinates, overlay, bounding }) => {
    if (!coordinates.length) return [];
    const p = coordinates[0];
    const text = overlay.extendData?.text || 'Phase A';
    const color = overlay.extendData?.color || '#FFC107';

    return [
      // 垂直虚线：从顶到底
      {
        type: 'line',
        attrs: {
          coordinates: [
            { x: p.x, y:0 },
            { x: p.x, y: bounding.height },
          ],
        },
        styles: { style: 'dashed', color, size: 1, dashedValue: [6, 4] },
      },
      //顶部文字标签
      {
        type: 'rectText',
        attrs: {
          x: p.x,
          y: 8,
          text,
          align: 'center',
          baseline: 'top',
        },
        styles: {
          style: 'fill',
          color: '#FFF',
          size: 10,
          family: 'monospace',
          backgroundColor: color,
          borderRadius: 3,
          paddingLeft: 6,
          paddingRight: 6,
          paddingTop: 2,
          paddingBottom: 2,
        },
      },
    ];
  },
});
```

---

### 施工验收标准（P1 图表层）

1. ChartWidget 接受 `chartExtension` prop，不传时行为与 P0 一致
2. 画完 overlay 后触发 `onDrawComplete`，bindPoint 坐标正确
3. 点击已有 overlay 触发 `onOverlayClick`，overlayId 正确
4.磁吸模式生效：`strong_magnet` 时画线自动吸附 K 线 OHLC
5. phaseMarker 显示垂直虚线 + 顶部文字标签
6. 数据加载失败时不渲染垃圾数据（response.ok 检查）