import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Catches render-time errors anywhere in the tree so a single bad component
 * shows a recoverable panel instead of white-screening the whole console. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full items-center justify-center p-6">
          <div className="max-w-lg rounded-xl border border-bad/40 bg-panel p-6 text-center">
            <h1 className="mb-2 text-sm font-semibold text-bad">
              Something went wrong rendering this view
            </h1>
            <p className="mb-4 font-mono text-xs text-ink-dim">
              {this.state.error.message}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="rounded-md border border-accent/50 bg-accent/15 px-4 py-1.5 text-xs font-medium text-accent hover:bg-accent/25"
            >
              Dismiss and retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
