interface CandleData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

self.onmessage = (e: MessageEvent) => {
  const { type, buffer, id } = e.data;

  if (type === 'decode') {
    try {
      const raw = new Float64Array(buffer);
      const candles: CandleData[] = [];

      for (let i = 0; i < raw.length; i += 6) {
        candles.push({
          timestamp: raw[i],
          open: raw[i + 1],
          high: raw[i + 2],
          low: raw[i + 3],
          close: raw[i + 4],
          volume: raw[i + 5],
        });
      }

      self.postMessage({ type: 'decoded', candles, id });
    } catch (err) {
      self.postMessage({ type: 'error', error: String(err), id });
    }
  }
};
