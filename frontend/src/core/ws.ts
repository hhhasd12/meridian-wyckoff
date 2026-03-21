/** WebSocket manager — topic subscription with auto-reconnect */

import type {
  WsClientMessage,
  WsServerMessage,
  WsTopicType,
} from "../types/api";

export type WsStatus = "connecting" | "connected" | "disconnected" | "error";
type MessageHandler = (msg: WsServerMessage) => void;
type StatusHandler = (status: WsStatus) => void;

export class WsManager {
  private ws: WebSocket | null = null;
  private url: string;
  private topics: WsTopicType[];
  private onMessage: MessageHandler;
  private onStatus: StatusHandler;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private retryCount = 0;
  private maxRetries = 20;
  private disposed = false;

  constructor(
    url: string,
    topics: WsTopicType[],
    onMessage: MessageHandler,
    onStatus: StatusHandler,
  ) {
    this.url = url;
    this.topics = topics;
    this.onMessage = onMessage;
    this.onStatus = onStatus;
  }

  connect(): void {
    if (this.disposed) return;
    this.cleanup();
    this.onStatus("connecting");

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.onStatus("error");
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.retryCount = 0;
      this.onStatus("connected");

      const sub: WsClientMessage = {
        type: "subscribe",
        topics: this.topics,
      };
      this.ws?.send(JSON.stringify(sub));

      // Heartbeat every 30s
      this.pingTimer = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: "ping" }));
        }
      }, 30_000);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as WsServerMessage;
        this.onMessage(msg);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.onStatus("disconnected");
      this.clearPing();
      if (!this.disposed) this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.onStatus("error");
    };
  }

  disconnect(): void {
    this.disposed = true;
    this.cleanup();
  }

  private cleanup(): void {
    this.clearPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.close();
      }
      this.ws = null;
    }
  }

  private clearPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.retryCount >= this.maxRetries || this.disposed) return;
    const delay = Math.min(1000 * 2 ** this.retryCount, 30_000);
    this.retryCount++;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }
}

/** Build WS URL relative to current page */
export function buildWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/realtime`;
}
