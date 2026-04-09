import { registerOverlay } from 'klinecharts';

function hexToRgba(hex: string, alpha: number): string {
  const c = hex.replace('#', '');
  if (c.length === 6) {
    const r = parseInt(c.slice(0, 2), 16);
    const g = parseInt(c.slice(2, 4), 16);
    const b = parseInt(c.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return hex;
}

registerOverlay({
  name: 'callout',
  totalStep: 2,
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    if (!coordinates.length) return [];
    const p = coordinates[0];
    // 优先使用 extendData.text，其次 extendData.eventType，兜底 'SC'
    const text = overlay.extendData?.text || overlay.extendData?.eventType || 'SC';
    const color = overlay.extendData?.color || '#FF5252';

    return [
      // 背景矩形 + 文字标签
      {
        type: 'rectText',
        attrs: { x: p.x, y: p.y - 25, text, align: 'center', baseline: 'middle' },
        styles: {
          style: 'fill',
          color: '#FFF',
          size: 11,
          family: 'monospace',
          weight: 'bold',
          backgroundColor: color,
          borderRadius: 3,
          borderSize: 0,
          borderColor: 'transparent',
          paddingLeft: 6,
          paddingRight: 6,
          paddingTop: 3,
          paddingBottom: 3
        }
      },
      // 虚线连接到K线
      {
        type: 'line',
        attrs: { coordinates: [{ x: p.x, y: p.y - 14 }, p] },
        styles: { style: 'dashed', color, size: 1, dashedValue: [3, 3] }
      }
    ];
  }
});
