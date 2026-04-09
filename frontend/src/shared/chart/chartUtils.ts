export const TYPE_MAP: Record<string, string> = {
  trend_line: 'segment',
  parallel_channel: 'parallelChannel',
  horizontal_line: 'horizontalStraightLine',
  vertical_line: 'verticalStraightLine',
  rectangle: 'rect',
  callout: 'callout',
  phase_marker: 'phaseMarker'
};

const REV: Record<string, string> = {};
Object.entries(TYPE_MAP).forEach(([k, v]) => REV[v] = k);

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
 * 检查 overlay 的点是否有有效坐标（timestamp + value 都存在）
 * KLineChart 的 Point 是 Partial<Point>，画在空图表时 timestamp 可能为 undefined
 */
export function isValidOverlayPoint(p: any): boolean {
  return p != null && typeof p.timestamp === 'number' && typeof p.value === 'number';
}

export function overlayToDrawing(o: any, symbol: string, tf: string) {
  const points = (o.points || [])
    .filter(isValidOverlayPoint)
    .map((p: any) => ({ time: p.timestamp, price: p.value }));

  return {
    id: o.id || o.overlayId || crypto.randomUUID(),
    symbol,
    type: REV[o.name] || o.name,
    points,
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
 * 检查 Drawing 是否有足够的有效点可以保存
 */
export function isDrawingValid(drawing: any): boolean {
  return drawing.points != null && drawing.points.length > 0;
}

const TF_HIER = ['5m', '15m', '1h', '4h', '1d', '1w'];

export function shouldShowDrawing(drawingTf: string, currentTf: string) {
  return TF_HIER.indexOf(drawingTf) >= TF_HIER.indexOf(currentTf);
}
