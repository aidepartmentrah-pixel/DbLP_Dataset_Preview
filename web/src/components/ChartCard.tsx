import type { ReactNode } from "react";

import type { ApiState } from "../lib/useApi";

interface ChartCardProps<T> {
  title: string;
  subtitle?: string;
  state: ApiState<T>;
  children: (data: T) => ReactNode;
  className?: string;
}

/** Card shell shared by every dashboard widget: §9.3 says every chart needs
 * a title stating the finding, a muted subtitle, an empty state and a
 * loading skeleton. */
export default function ChartCard<T>({ title, subtitle, state, children, className }: ChartCardProps<T>) {
  return (
    <div className={`card chart-card${className ? ` ${className}` : ""}`}>
      <h3 className="chart-title">{title}</h3>
      {subtitle && <p className="chart-subtitle">{subtitle}</p>}
      {state.status === "loading" && <div className="chart-skeleton" aria-label="Loading" />}
      {state.status === "error" && <p className="chart-empty">Couldn't load this chart: {state.error}</p>}
      {state.status === "empty" && <p className="chart-empty">No data yet.</p>}
      {state.status === "ready" && children(state.data)}
    </div>
  );
}
