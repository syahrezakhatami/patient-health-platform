import { Component, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  failed: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(): void {
    // Do not render stacks, tokens, or API payloads.
  }

  render(): ReactNode {
    if (this.state.failed) {
      return (
        <section className="panel" role="alert">
          <h1>Something went wrong</h1>
          <p>Reload the page and sign in again if needed.</p>
        </section>
      );
    }
    return this.props.children;
  }
}
