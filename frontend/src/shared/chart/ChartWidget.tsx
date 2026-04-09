import { useRef, useEffect } from 'react';
import { init, dispose, Chart, CandleType, OverlayMode } from 'klinecharts';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { useDataWorker } from '../../workers/useDataWorker';
import { cache } from '../../services/cache';
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
  // 跟踪已渲染的 overlay id 集合，用于增量同步
  const renderedIds = useRef<Set<string>>(new Set());
  const { symbol, timeframe } = useAppStore();
  const focusBarIndex = useAppStore(s => s.focusBarIndex);
  const { drawings } = useDrawingStore();
  const { decodeCandles } = useDataWorker();

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
          type: CandleType.CandleSolid,
          bar: {
            upColor: '#26a69a',
            downColor: '#ef5350',
            noChangeColor: '#888'
          }
        }
      }
    });
    chart.current!.createIndicator('VOL', false, { id: 'vol' });
    return () => { if (ref.current) dispose(ref.current); };
  }, []);

  // ② 数据加载 — 优先 IndexedDB 缓存，未命中再 fetch 后端
  useEffect(() => {
    if (!chart.current) return;
    (async () => {
      try {
        let buffer = await cache.getCandles(symbol, timeframe);
        if (!buffer) {
          const response = await fetch(`/api/datasource/candles/${symbol}/${timeframe}`);
          if (!response.ok) throw new Error(`K线加载失败 ${response.status}`);
          buffer = await response.arrayBuffer();
          await cache.setCandles(symbol, timeframe, buffer);
        }
        const candles = await decodeCandles(buffer);
        chart.current!.applyNewData(candles);
      } catch (err) {
        console.error('[ChartWidget] 加载K线失败:', err);
      }
    })();
  }, [symbol, timeframe, decodeCandles]);

  // ③ overlay 同步 — 增量更新，避免闪烁
  useEffect(() => {
    if (!chart.current) return;

    const prevIds = renderedIds.current;

    // 计算应该显示的 drawing id 集合
    const targetIds = new Set<string>();
    drawings.forEach(d => {
      if (shouldShowDrawing(d.properties.timeframe || timeframe, timeframe)) {
        targetIds.add(d.id);
      }
    });

    // 删除不再需要的 overlay
    prevIds.forEach(id => {
      if (!targetIds.has(id)) {
        chart.current!.removeOverlay(id);
      }
    });

    // 添加新增的 overlay / 更新已有 overlay 的属性（颜色、文字等）
    targetIds.forEach(id => {
      const d = drawings.get(id);
      if (!d) return;

      const overlayConfig = {
        ...drawingToOverlay(d),
        onClick: (kEvent: any) => {
          chartExtension?.onOverlayClick?.({
            overlayId: kEvent.overlay?.id || d.id,
            name: kEvent.overlay?.name || d.type,
            points: (kEvent.overlay?.points || []).map((p: any) => ({
              timestamp: p.timestamp,
              value: p.value,
            })),
            extendData: kEvent.overlay?.extendData,
          });
        },
        onPressedMoveEnd: (kEvent: any) => {
          chartExtension?.onOverlayMoveEnd?.({
            overlayId: kEvent.overlay?.id || d.id,
            name: kEvent.overlay?.name || d.type,
            points: (kEvent.overlay?.points || []).map((p: any) => ({
              timestamp: p.timestamp,
              value: p.value,
            })),
            extendData: kEvent.overlay?.extendData,
          });
        },
      } as any;

      if (prevIds.has(id)) {
        // W1修复：已有overlay属性变化（颜色/文字）→ remove + create 强制刷新
        chart.current!.removeOverlay(id);
        chart.current!.createOverlay(overlayConfig);
      } else {
        chart.current!.createOverlay(overlayConfig);
      }
    });

    // 更新已渲染集合
    renderedIds.current = targetIds;
  }, [drawings, timeframe, chartExtension]);

  // ④ focusBarIndex 监听 — 从面板点击事件定位到K线
  useEffect(() => {
    if (focusBarIndex === null || !chart.current) return;
    chart.current.scrollToDataIndex(focusBarIndex, 300);
    useAppStore.getState().setFocusBarIndex(null);
  }, [focusBarIndex]);

  useEffect(() => {
    if (!chart.current || !currentTool || currentTool === 'cursor') return;

    const overlayName = TYPE_MAP[currentTool];
    if (!overlayName) return;

    const toEvent = (kEvent: any): OverlayEvent => {
      const rawPoints: Array<Partial<{ timestamp: number; value: number; dataIndex: number }>> =
        kEvent.overlay?.points || [];
      return {
        overlayId: kEvent.overlay?.id || '',
        name: kEvent.overlay?.name || '',
        points: rawPoints
          .filter((p: any) => typeof p.timestamp === 'number' && typeof p.value === 'number')
          .map((p: any) => ({
            timestamp: p.timestamp,
            value: p.value,
          })),
        extendData: kEvent.overlay?.extendData,
      };
    };

    // 映射磁吸模式字符串到 KLineChart 枚举
    const modeMap: Record<string, OverlayMode> = {
      normal: OverlayMode.Normal,
      weak_magnet: OverlayMode.WeakMagnet,
      strong_magnet: OverlayMode.StrongMagnet,
    };

    chart.current!.createOverlay({
      name: overlayName,
      mode: modeMap[chartExtension?.magnetMode || 'normal'] || OverlayMode.Normal,

      onDrawEnd: (kEvent: any) => {
        chartExtension?.onDrawComplete?.(
          toEvent(kEvent),
          { x: kEvent.bindPoint?.x ?? 0, y: kEvent.bindPoint?.y ?? 0 }
        );
        return true;
      },

      onClick: (kEvent: any) => {
        chartExtension?.onOverlayClick?.(toEvent(kEvent));
      },

      onPressedMoveEnd: (kEvent: any) => {
        chartExtension?.onOverlayMoveEnd?.(toEvent(kEvent));
      },
    } as any);
  }, [currentTool, chartExtension]);

  return <div ref={ref} style={{ flex: 1 }} />;
}
