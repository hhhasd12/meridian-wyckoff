import { useRef, useCallback } from 'react';

let msgId = 0;

export function useDataWorker() {
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<Map<number, { resolve: Function; reject: Function }>>(new Map());

  const getWorker = useCallback(() => {
    if (!workerRef.current) {
      const w = new Worker(
        new URL('./dataWorker.ts', import.meta.url),
        { type: 'module' }
      );
      // W6: onerror 处理
      w.onerror = (e) => {
        console.error('[dataWorker] 错误:', e);
        pendingRef.current.forEach(({ reject }) => reject(new Error('Worker错误')));
        pendingRef.current.clear();
      };
      // W7: 消息ID匹配请求/响应
      w.onmessage = (e: MessageEvent) => {
        if (!e.data?.id && e.data?.type !== 'decoded') return;
        const entry = pendingRef.current.get(e.data.id);
        if (entry) {
          pendingRef.current.delete(e.data.id);
          entry.resolve(e.data.candles);
        }
      };
      workerRef.current = w;
    }
    return workerRef.current;
  }, []);

  const decodeCandles = useCallback((buffer: ArrayBuffer): Promise<any[]> => {
    return new Promise((resolve, reject) => {
      const id = ++msgId;
      pendingRef.current.set(id, { resolve, reject });
      const worker = getWorker();
      worker.postMessage({ type: 'decode', buffer, id }, [buffer]);
    });
  }, [getWorker]);

  return { decodeCandles };
}
