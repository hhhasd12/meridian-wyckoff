export interface OverlayEvent {
  overlayId: string;
  name: string;
  points: { timestamp: number; value: number }[];
  extendData?: Record<string, any>;
}

export interface ChartExtension {
  onDrawComplete?: (event: OverlayEvent, bindPoint: { x: number; y: number }) => void;
  onOverlayClick?: (event: OverlayEvent) => void;
  onOverlayMoveEnd?: (event: OverlayEvent) => void;
  magnetMode?: 'normal' | 'weak_magnet' | 'strong_magnet';
}
