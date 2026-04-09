import Dexie from 'dexie';

class MeridianCache extends Dexie {
  candles!: Dexie.Table<{ key: string; data: ArrayBuffer; timestamp: number }>;

  constructor() {
    super('meridian-cache');
    this.version(1).stores({ candles: 'key' });
  }

  async getCandles(symbol: string, tf: string) {
    const record = await this.candles.get(`${symbol}:${tf}`);
    return record?.data ?? null;
  }

  async setCandles(symbol: string, tf: string, data: ArrayBuffer) {
    await this.candles.put({
      key: `${symbol}:${tf}`,
      data,
      timestamp: Date.now()
    });
  }
}
export const cache = new MeridianCache();
