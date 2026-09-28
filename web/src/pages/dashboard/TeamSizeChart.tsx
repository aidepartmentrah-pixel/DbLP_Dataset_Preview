import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { accentColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface TeamSizeRow {
  year: number;
  paper_count: number;
  median: number;
  p25: number;
  p75: number;
}

export default function TeamSizeChart() {
  const state = useApi<TeamSizeRow[]>("/api/dashboard/team-size", (d) => d.length === 0);
  const rows = state.status === "ready" ? state.data : [];

  // IQR band drawn as a transparent "floor" stacked series (p25) plus a
  // filled "band height" series (p75 - p25) on top of it.
  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: {
            trigger: "axis",
            formatter: (params: any) => {
              const p = Array.isArray(params) ? params.find((s: any) => s.seriesName === "Median") : params;
              const row = rows[p.dataIndex];
              return `${row.year}<br/>median ${row.median}, IQR ${row.p25}–${row.p75}`;
            },
          },
          grid: { left: 48, right: 24, top: 24, bottom: 32 },
          xAxis: { type: "category", data: rows.map((r) => r.year) },
          yAxis: { type: "value", name: "Authors per paper" },
          series: [
            { name: "p25 floor", type: "line", stack: "iqr", data: rows.map((r) => r.p25), lineStyle: { opacity: 0 }, showSymbol: false, tooltip: { show: false } },
            { name: "IQR", type: "line", stack: "iqr", data: rows.map((r) => r.p75 - r.p25), lineStyle: { opacity: 0 }, areaStyle: { color: accentColor(), opacity: 0.15 }, showSymbol: false, tooltip: { show: false } },
            { name: "Median", type: "line", data: rows.map((r) => r.median), color: accentColor(), showSymbol: false, z: 3 },
          ],
        }
      : null;
  const chartRef = useChart(option);

  const subtitle =
    rows.length > 1
      ? `Median team size: ${rows[0].median} (${rows[0].year}) -> ${rows[rows.length - 1].median} (${rows[rows.length - 1].year})`
      : undefined;

  return (
    <ChartCard title="Team size over time" subtitle={subtitle} state={state}>
      {() => <div ref={chartRef} className="chart-canvas" />}
    </ChartCard>
  );
}
