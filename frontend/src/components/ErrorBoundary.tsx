import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** When this changes (e.g. the route pathname), a caught error is cleared
   *  so one crashed page doesn't blank every subsequent navigation. */
  resetKey?: string | number;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] Uncaught render error:", error, info);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-background p-6">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-sm text-center space-y-4">
            <h1 className="text-xl font-semibold text-foreground">Something went wrong</h1>
            <p className="text-sm text-muted-foreground">
              An unexpected error occurred. Please reload the page to continue.
            </p>
            {process.env.NODE_ENV === "development" && this.state.error && (
              <pre className="mt-2 rounded-md bg-muted p-3 text-left text-xs text-foreground overflow-auto max-h-40">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={() => window.location.reload()}
              className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
