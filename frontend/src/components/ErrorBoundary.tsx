import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Without this, a render error anywhere in the tree unmounts the whole app and
 * leaves a blank page with nothing but a console trace. A long pipeline run is
 * expensive; the user should at least be told what broke.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="grid min-h-screen place-items-center bg-slate-50 p-6 dark:bg-slate-950">
        <div className="card max-w-md p-6 text-center">
          <AlertTriangle size={32} className="mx-auto text-amber-500" />
          <h1 className="mt-3 text-lg font-bold text-slate-800 dark:text-slate-100">
            Something broke in the interface
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            The pipeline itself is unaffected — your run history is stored on the server.
          </p>
          <pre className="mt-3 max-h-32 overflow-auto rounded-lg bg-slate-100 p-3 text-left text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {error.message}
          </pre>
          <button onClick={this.reset} className="btn-primary mx-auto mt-4">
            <RotateCcw size={15} />
            Try again
          </button>
        </div>
      </div>
    );
  }
}
