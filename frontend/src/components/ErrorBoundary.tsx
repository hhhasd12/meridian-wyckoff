/** ErrorBoundary — 捕获 React 渲染错误，防止白屏 */

import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("React ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: 40,
            background: "#131722",
            color: "#D1D4DC",
            fontFamily: "monospace",
            height: "100vh",
          }}
        >
          <h2 style={{ marginBottom: 16 }}>UI Rendering Error</h2>
          <pre
            style={{
              color: "#EF5350",
              whiteSpace: "pre-wrap",
              fontSize: 13,
              marginBottom: 24,
            }}
          >
            {this.state.error?.message}
            {"\n\n"}
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "8px 16px",
              background: "#5B9CF6",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
