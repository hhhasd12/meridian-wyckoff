import { useState, useEffect, useMemo } from 'react';
import { ChartWidget } from '../../shared/chart/ChartWidget';
import { DrawingToolbar } from '../../shared/chart/DrawingToolbar';
import { AnnotationPanel } from './panels/AnnotationPanel';
import { FeaturePanel } from './panels/FeaturePanel';
import { BacktestPanel } from './panels/BacktestPanel';
import { EvolutionPanel } from './panels/EvolutionPanel';
import { EngineStatePanel } from './panels/EngineStatePanel';
import { EventTypePopup } from './components/EventTypePopup';
import { PhaseSelectPopup } from './components/PhaseSelectPopup';
import { useAppStore } from '../../stores/appStore';
import { useDrawingStore } from '../../stores/drawingStore';
import { fetchSymbols, fetchDrawings, saveDrawing, updateDrawingApi, deleteDrawingApi } from '../../services/api';
import { setupKeyboard } from '../../utils/keyboard';
import { overlayToDrawing, isDrawingValid } from '../../shared/chart/chartUtils';
import { ChartExtension, OverlayEvent } from '../../shared/chart/types';
import { WyckoffEventDef, WyckoffPhaseDef } from './config/wyckoffEvents';

type PopupState =
  | null
  | { type: 'eventType'; overlay: OverlayEvent; position: { x: number; y: number } }
  | { type: 'phase'; overlay: OverlayEvent; position: { x: number; y: number } };

type SidebarTab = 'annotate' | 'backtest' | 'evolution' | 'engine';

const TABS = [
  { id: 'annotate' as const, icon: '📋', label: '标注' },
  { id: 'backtest' as const, icon: '🧪', label: '回测' },
  { id: 'evolution' as const, icon: '🧬', label: '进化' },
  { id: 'engine' as const, icon: '⚙', label: '引擎' },
];

export function EvolutionPage() {
  const [tool, setTool] = useState('cursor');
  const [popup, setPopup] = useState<PopupState>(null);
  const [activeTab, setActiveTab] = useState<SidebarTab>('annotate');
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbolOpen, setSymbolOpen] = useState(false);
  const { symbol, timeframe, setTimeframe, setSymbol } = useAppStore();
  const { drawings, selectedId, addDrawing, selectDrawing, loadDrawings } = useDrawingStore();
  const sel = selectedId ? drawings.get(selectedId) : null;

  // 加载 symbol 列表
  useEffect(() => {
    fetchSymbols()
      .then((arr: string[]) => { if (Array.isArray(arr)) setSymbols(arr); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchDrawings(symbol).then(arr => {
      if (Array.isArray(arr)) loadDrawings(arr);
    }).catch(console.error);
  }, [symbol]);

  useEffect(() => {
    const undo = useDrawingStore.temporal.getState().undo;
    const redo = useDrawingStore.temporal.getState().redo;
    const del = () => {
      if (selectedId) {
        deleteDrawingApi(symbol, selectedId).catch(console.error);
        useDrawingStore.getState().deleteDrawing(selectedId);
      }
    };
    return setupKeyboard(setTool, undo, redo, del);
  }, [selectedId]);

  const chartExtension = useMemo<ChartExtension>(() => ({
    magnetMode: 'strong_magnet',

    onDrawComplete: (event: OverlayEvent, bindPoint: { x: number; y: number }) => {
      if (event.name === 'callout') {
        setPopup({ type: 'eventType', overlay: event, position: bindPoint });
      } else if (event.name === 'phaseMarker') {
        setPopup({ type: 'phase', overlay: event, position: bindPoint });
      } else {
        const drawing = overlayToDrawing(event, symbol, timeframe);
        if (!isDrawingValid(drawing)) {
          console.warn('[EvolutionPage] 标注坐标无效（图表数据可能未加载），已忽略');
          setTool('cursor');
          return;
        }
        addDrawing(drawing);
        saveDrawing(symbol, drawing).catch(console.error);
      }
      setTool('cursor');
    },

    onOverlayClick: (event: OverlayEvent) => {
      selectDrawing(event.overlayId);
    },

    onOverlayMoveEnd: (event: OverlayEvent) => {
      const drawing = overlayToDrawing(event, symbol, timeframe);
      updateDrawingApi(symbol, event.overlayId, {
        points: drawing.points,
        updated_at: new Date().toISOString(),
      }).catch(console.error);
    },
  }), [symbol, timeframe, addDrawing, selectDrawing]);

  const handleEventSelect = (eventDef: WyckoffEventDef) => {
    if (!popup || popup.type !== 'eventType') return;
    const drawing = overlayToDrawing(popup.overlay, symbol, timeframe);
    if (!isDrawingValid(drawing)) {
      console.warn('[EvolutionPage] 气泡坐标无效，已忽略');
      setPopup(null);
      return;
    }
    drawing.properties.eventType = eventDef.id;
    drawing.properties.text = eventDef.label;
    drawing.properties.color = eventDef.color;
    addDrawing(drawing);
    saveDrawing(symbol, drawing).catch(console.error);
    setPopup(null);
  };

  const handlePhaseSelect = (phaseDef: WyckoffPhaseDef) => {
    if (!popup || popup.type !== 'phase') return;
    const drawing = overlayToDrawing(popup.overlay, symbol, timeframe);
    if (!isDrawingValid(drawing)) {
      console.warn('[EvolutionPage] 阶段标记坐标无效，已忽略');
      setPopup(null);
      return;
    }
    drawing.properties.phase = phaseDef.id;
    drawing.properties.text = phaseDef.label;
    drawing.properties.color = phaseDef.color;
    addDrawing(drawing);
    saveDrawing(symbol, drawing).catch(console.error);
    setPopup(null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-primary)' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 12px', borderBottom: '1px solid var(--border)',
      }}>
        {/* Symbol 选择器 */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setSymbolOpen(!symbolOpen)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)',
              background: 'var(--bg-secondary)', color: 'var(--text-primary)',
              cursor: 'pointer', fontSize: 14, fontWeight: 600,
            }}
          >
            {symbol}
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>▾</span>
          </button>
          {symbolOpen && (
            <>
              <div onClick={() => setSymbolOpen(false)} style={{
                position: 'fixed', inset: 0, zIndex: 998, background: 'transparent',
              }} />
              <div style={{
                position: 'absolute', top: '100%', left: 0, marginTop: 2,
                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                borderRadius: 6, zIndex: 999, maxHeight: 240, overflowY: 'auto',
                boxShadow: '0 4px 16px rgba(0,0,0,0.4)', minWidth: 120,
              }}>
                {symbols.map(s => (
                  <button key={s} onClick={() => { setSymbol(s); setSymbolOpen(false); }} style={{
                    display: 'block', width: '100%', padding: '6px 12px',
                    border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 12,
                    background: s === symbol ? 'var(--accent)' : 'transparent',
                    color: 'var(--text-primary)',
                  }}>{s}</button>
                ))}
                {!symbols.length && (
                  <div style={{ padding: '8px 12px', fontSize: 11, color: 'var(--text-muted)' }}>
                    加载中...
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        {['5m', '15m', '1h', '4h', '1d', '1w'].map(tf => (
          <button key={tf} onClick={() => setTimeframe(tf)} style={{
            padding: '4px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 12,
            background: tf === timeframe ? 'var(--accent)' : 'transparent',
            color: 'var(--text-primary)',
          }}>{tf}</button>
        ))}
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <DrawingToolbar currentTool={tool} onToolChange={setTool} />
        <ChartWidget currentTool={tool} chartExtension={chartExtension} />
        <div style={{
          width: 280,
          borderLeft: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-secondary)',
        }}>
          {/* Tab栏 */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border)',
            flexShrink: 0,
          }}>
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  flex: 1,
                  padding: '8px 0',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 11,
                  background: activeTab === tab.id ? 'var(--bg-primary)' : 'transparent',
                  color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
                  borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
                }}
              >
                {tab.icon} {tab.label}
              </button>
            ))}
          </div>

          {/* Tab内容 */}
          <div style={{ flex: 1, overflow: 'auto' }}>
            {activeTab === 'annotate' && (
              <>
                <AnnotationPanel />
                {sel && <FeaturePanel drawing={sel} />}
              </>
            )}
            {activeTab === 'backtest' && <BacktestPanel />}
            {activeTab === 'evolution' && <EvolutionPanel />}
            {activeTab === 'engine' && <EngineStatePanel />}
          </div>
        </div>
      </div>

      {popup?.type === 'eventType' && (
        <EventTypePopup
          position={popup.position}
          onSelect={handleEventSelect}
          onCancel={() => setPopup(null)}
        />
      )}
      {popup?.type === 'phase' && (
        <PhaseSelectPopup
          position={popup.position}
          onSelect={handlePhaseSelect}
          onCancel={() => setPopup(null)}
        />
      )}

      <div style={{
        padding: '4px 12px', borderTop: '1px solid var(--border)',
        fontSize: 11, color: 'var(--text-muted)',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span>标注: {drawings.size} · {symbol} · {timeframe}</span>
        <span style={{ color: 'var(--text-muted)' }}>Meridian</span>
      </div>
    </div>
  );
}
