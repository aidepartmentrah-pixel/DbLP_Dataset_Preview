import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { accentColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface VenueRow {
  venue: string;
  name: string;
  type: string;
  paper_count: number;
}

export default function TopVenuesChart() {
  const state = useApi<VenueRow[]>("/api/dashboard/top-venues?limit=15", (d) => d.length === 0);
  const rows = state.status === "ready" ? [...state.data].reverse() : [];

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: { trigger: "axis", valueFormatter: (v) => `${v} papers` },
          grid: { left: 120, right: 24, top: 12, bottom: 24 },
          xAxis: { type: "value", name: "Papers" },
          yAxis: { type: "category", data: rows.map((r) => r.venue) },
          series: [{ type: "bar", data: rows.map((r) => r.paper_count), color: accentColor() }],
        }
      : null;
  const chartRef = useChart(option);

  const top = state.status === "ready" ? state.data[0] : null;
  const subtitle = top ? `${top.venue} leads with ${top.paper_count.toLocaleString()} papers` : undefined;

  return (
    <ChartCard title="Top 15 venues" subtitle={subtitle} state={state}>
      {() => <div ref={chartRef} className="chart-canvas" />}
    </ChartCard>
  );
}
