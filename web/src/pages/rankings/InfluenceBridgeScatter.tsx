import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { accentColor, mutedColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface ScatterRow {
  author_id: number;
  name: string;
  pagerank_percentile: number;
  betweenness_percentile: number;
}

export default function InfluenceBridgeScatter() {
  const state = useApi<ScatterRow[]>("/api/metrics/scatter", (d) => d.length === 0);
  const rows = state.status === "ready" ? state.data : [];

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: {
            formatter: (p: any) =>
              `${p.data[2]}<br/>PageRank pctl: ${p.data[0]}, Betweenness pctl: ${p.data[1]}`,
          },
          grid: { left: 56, right: 24, top: 24, bottom: 40 },
          xAxis: { type: "value", name: "PageRank percentile", min: 0, max: 100 },
          yAxis: { type: "value", name: "Betweenness percentile", min: 0, max: 100 },
          series: [
            {
              type: "scatter", symbolSize: 5, color: accentColor(),
              data: rows.map((r) => [r.pagerank_percentile, r.betweenness_percentile, r.name]),
              markLine: {
                symbol: "none",
                lineStyle: { color: mutedColor(), type: "dashed" },
                data: [{ xAxis: 50 }, { yAxis: 50 }],
              },
            },
          ],
        }
      : null;
  const chartRef = useChart(option);

  return (
    <ChartCard
      title="Influence x bridge"
      subtitle="Hub (right), bridge (top), both (top-right), peripheral (bottom-left)"
      state={state}
      className="span-12"
    >
      {() => <div ref={chartRef} className="chart-canvas" style={{ height: 420 }} />}
    </ChartCard>
  );
}
