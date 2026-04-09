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
  name: 'phaseMarker',
  totalStep: 3,
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, overlay, bounding }) => {
    if (!coordinates.length) return [];
    const text = overlay.extendData?.text || 'Phase A';
    const color = overlay.extendData?.color || '#FFC107';
    const figs: any[] = [];

    // 单点模式（向后兼容旧数据）：只画一条垂直虚线
    if (coordinates.length === 1) {
      const p = coordinates[0];
      figs.push(
        {
          type: 'line',
          attrs: { coordinates: [{ x: p.x, y: 0 }, { x: p.x, y: bounding.height }] },
          styles: { style: 'dashed', color, size: 1, dashedValue: [6, 4] },
        },
        {
          type: 'rectText',
          attrs: { x: p.x, y: 8, text, align: 'center', baseline: 'top' },
          styles: {
            style: 'fill', color: '#FFF', size: 10, family: 'monospace', weight: 'bold',
            backgroundColor: color, borderRadius: 3, borderSize: 0, borderColor: 'transparent',
            paddingLeft: 6, paddingRight: 6, paddingTop: 2, paddingBottom: 2,
          },
        }
      );
      return figs;
    }

    // 双点模式：两条垂直虚线 + 半透明填充 + 顶部标签
    const p1 = coordinates[0];
    const p2 = coordinates[1];
    const x1 = Math.min(p1.x, p2.x);
    const x2 = Math.max(p1.x, p2.x);
    const centerX = (x1 + x2) / 2;

    // 半透明填充区域
    figs.push({
      type: 'polygon',
      attrs: {
        coordinates: [
          { x: x1, y: 0 },
          { x: x2, y: 0 },
          { x: x2, y: bounding.height },
          { x: x1, y: bounding.height },
        ],
      },
      styles: { style: 'fill', color: hexToRgba(color, 0.06) },
    });

    // 左侧垂直虚线
    figs.push({
      type: 'line',
      attrs: { coordinates: [{ x: x1, y: 0 }, { x: x1, y: bounding.height }] },
      styles: { style: 'dashed', color, size: 1, dashedValue: [6, 4] },
    });

    // 右侧垂直虚线
    figs.push({
      type: 'line',
      attrs: { coordinates: [{ x: x2, y: 0 }, { x: x2, y: bounding.height }] },
      styles: { style: 'dashed', color, size: 1, dashedValue: [6, 4] },
    });

    // 顶部文字标签（居中）
    figs.push({
      type: 'rectText',
      attrs: { x: centerX, y: 8, text, align: 'center', baseline: 'top' },
      styles: {
        style: 'fill', color: '#FFF', size: 10, family: 'monospace', weight: 'bold',
        backgroundColor: color, borderRadius: 3, borderSize: 0, borderColor: 'transparent',
        paddingLeft: 6, paddingRight: 6, paddingTop: 2, paddingBottom: 2,
      },
    });

    return figs;
  },
});
