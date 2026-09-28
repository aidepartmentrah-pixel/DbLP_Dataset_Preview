import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { accentColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface ProductivityRow {
  papers: number;
  authors: number;
}

export default function ProductivityChart() {
  const state = useApi<ProductivityRow[]>("/api/dashboard/productivity", (d) => d.length === 0);
  const rows = state.status === "ready" ? state.data : [];

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: { formatter: (p: any) => `${p.data[1].toLocaleString()} authors wrote exactly ${p.data[0]} paper(s)` },
          grid: { left: 56, right: 24, top: 24, bottom: 40 },
          xAxis: { type: "log", name: "Papers per author" },
          yAxis: { type: "log", name: "Authors" },
          series: [{
            type: "scatter", symbolSize: 6, color: accentColor(),
            data: rows.map((r) => [r.papers, r.authors]),
          }],
        }
      : null;
  const chartRef = useChart(option);

  const singlePaperShare =
    rows.length > 0
      ? (100 * (rows.find((r) => r.papers === 1)?.authors ?? 0) / rows.reduce((s, r) => s + r.authors, 0)).toFixed(0)
      : null;
  const subtitle = singlePaperShare ? `A long tail: ${singlePaperShare}% of authors have exactly one paper in scope` : undefined;

  return (
    <ChartCard title="Papers per author" subtitle={subtitle} state={state}>
      {() => <div ref={chartRef} className="chart-canvas" />}
    </ChartCard>
  );
}
