# Worker 性能层 (workers/) — Step 4

## 为什么要 Worker
主线程只做两件事：响应用户输入 + 渲染画面。
重计算（二进制解码、大数据处理）放到 Worker 后台线程，保证图表永远流畅。

P0 数据量不大时感知不明显，但架构从第一天就做对，后续加实盘数据（百万根K线）时不用重构。

## 文件清单

### 1. dataWorker.ts — 数据处理 Worker
负责：二进制 K线解码、数据预处理、未来可扩展技术指标计算。

```typescript
// dataWorker.ts — 在后台线程运行

/**
 * 消息协议：
 * 主线程 → Worker: { type: 'decode', buffer: ArrayBuffer }
 * Worker → 主线程: { type: 'decoded', candles: CandleData[] }
 */

interface CandleData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

self.onmessage = (e: MessageEvent) => {
  const { type, buffer } = e.data;

  if (type === 'decode') {
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

    // 传回主线程
    self.postMessage({ type: 'decoded', candles });
  }
};
```

### 2. useDataWorker.ts — 主线程 Hook
封装 Worker 通信，让组件用起来像普通异步函数。

```typescript
import { useRef, useCallback } from 'react';

export function useDataWorker() {
  const workerRef = useRef<Worker | null>(null);

  //懒初始化 Worker
  const getWorker = useCallback(() => {
    if (!workerRef.current) {
      workerRef.current = new Worker(
        new URL('./dataWorker.ts', import.meta.url),
        { type: 'module' }
      );
    }
    return workerRef.current;
  }, []);

  // 解码二进制K线数据
  const decodeCandles = useCallback((buffer: ArrayBuffer): Promise<any[]> => {
    return new Promise((resolve) => {
      const worker = getWorker();
      worker.onmessage = (e) => {
        if (e.data.type === 'decoded') {
          resolve(e.data.candles);
        }
      };
      // 用Transferable 传递buffer，零拷贝
      worker.postMessage({ type: 'decode', buffer }, [buffer]);
    });
  }, [getWorker]);

  return { decodeCandles };
}
```

### 3. 在 ChartWidget 中使用 Worker
替换原来主线程的同步解码：

```tsx
// 原来（主线程解码）：
const raw = await fetchCandles(symbol, timeframe);
chart.current.applyNewData(decodeCandlesFromBinary(raw));

// 改为（Worker 解码）：
const { decodeCandles } = useDataWorker();

useEffect(() => {
  (async () => {
    const response = await fetch(`/api/datasource/candles/${symbol}/${timeframe}`);
    const buffer = await response.arrayBuffer();
    const candles = await decodeCandles(buffer);
    chart.current!.applyNewData(candles);
  })();
}, [symbol, timeframe]);
```

## SharedArrayBuffer（P1升级路径）
P0 用postMessage + Transferable 传递数据（零拷贝但所有权转移）。
P1 可升级为 SharedArrayBuffer：K线数据在主线程和Worker 之间共享内存，完全零拷贝。

需要配置 HTTP 响应头：
```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

vite.config.ts 中添加：
```typescript
server: {
  headers: {
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Embedder-Policy': 'require-corp',
  }
}
```

P0 先不做，记住这个升级路径即可。

## 施工注意
- Vite 天然支持 `new Worker(new URL(...), { type: 'module' })`，无需额外配置
- Transferable 传递 ArrayBuffer 后，原引用失效（所有权转移），不要再读
- Worker 文件必须是独立的，不能 import 主线程的 React 组件
- Worker 内可以 import 纯函数工具（如数学计算）