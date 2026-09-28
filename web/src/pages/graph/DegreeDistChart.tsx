import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { accentColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface DegreeRow {
  degree: number;
  authors: number;
}

export default function DegreeDistChart() {
  const state = useApi<DegreeRow[]>("/api/graph/degree-dist", (d) => d.length === 0);
  const rows = state.status === "ready" ? state.data.filter((r) => r.degree > 0) : [];

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: { formatter: (p: any) => `${p.data[1].toLocaleString()} authors have ${p.data[0]} co-authors` },
          grid: { left: 56, right: 24, top: 24, bottom: 40 },
          xAxis: { type: "log", name: "Degree (k)" },
          yAxis: { type: "log", name: "P(k)" },
          series: [{ type: "scatter", symbolSize: 5, color: accentColor(), data: rows.map((r) => [r.degree, r.authors]) }],
        }
      : null;
  const chartRef = useChart(option);

  return (
    <ChartCard title="Degree distribution" subtitle="Log-log P(k) vs k - a straight line suggests a scale-free network" state={state} className="span-12">
      {() => <div ref={chartRef} className="chart-canvas" />}
    </ChartCard>
  );
}
