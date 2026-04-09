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
  name: 'parallelChannel',
  totalStep: 3,
  needDefaultPointFigure: true,
  needDefaultXAxisFigure: true,
  needDefaultYAxisFigure: true,
  createPointFigures: ({ coordinates, overlay }) => {
    const figs: any[] = [];
    const color = overlay.extendData?.color || '#2196F3';

    if (coordinates.length >= 2) {
      figs.push({
        type: 'line',
        attrs: { coordinates: [coordinates[0], coordinates[1]] },
        styles: { style: 'solid', color, size: 1.5 }
      });
    }

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
      // W4: 用 rgba() 替代 color+'15'，兼容所有颜色格式
      figs.push({
        type: 'polygon',
        attrs: { coordinates: [
          coordinates[0], coordinates[1],
          { x: coordinates[1].x, y: coordinates[1].y + oY },
          { x: coordinates[0].x, y: coordinates[0].y + oY }
        ]},
        styles: { style: 'fill', color: hexToRgba(color, 0.08) }
      });
    }
    return figs;
  },
  performEventPressedMove: ({ currentStep, points, performPoint }) => {
    if (currentStep === 3) performPoint.timestamp = points[0].timestamp;
  }
});
