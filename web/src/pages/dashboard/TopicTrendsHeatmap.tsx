import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { sequentialRamp } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface TopicRow {
  word: string;
  year: number;
  paper_count: number;
}

export default function TopicTrendsHeatmap() {
  const state = useApi<TopicRow[]>("/api/dashboard/topic-trends", (d) => d.length === 0);
  const rows = state.status === "ready" ? state.data : [];

  const years = Array.from(new Set(rows.map((r) => r.year))).sort((a, b) => a - b);
  const words = Array.from(new Set(rows.map((r) => r.word)));
  // Keep the word axis ordered by total mentions (most-discussed keyword first).
  const totals = new Map<string, number>();
  for (const r of rows) totals.set(r.word, (totals.get(r.word) ?? 0) + r.paper_count);
  words.sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0));

  const max = rows.reduce((m, r) => Math.max(m, r.paper_count), 0);
  const [rampLow, rampHigh] = sequentialRamp();

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: { formatter: (p: any) => `"${p.data[0]}" in ${p.data[1]}: ${p.data[2]} papers` },
          grid: { left: 100, right: 24, top: 12, bottom: 40 },
          xAxis: { type: "category", data: words, axisLabel: { rotate: 45 } },
          yAxis: { type: "category", data: years.map(String) },
          visualMap: {
            min: 0, max, orient: "horizontal", left: "center", bottom: 0,
            inRange: { color: [rampLow, rampHigh] },
          },
          series: [{
            type: "heatmap",
            data: rows.map((r) => [r.word, String(r.year), r.paper_count]),
          }],
        }
      : null;
  const chartRef = useChart(option);

  const topWord = words[0];
  const subtitle = topWord ? `"${topWord}" is the most-discussed keyword across the loaded scope` : undefined;

  return (
    <ChartCard title="Topic keywords by year" subtitle={subtitle} state={state} className="span-12">
      {() => <div ref={chartRef} className="chart-canvas" style={{ height: 420 }} />}
    </ChartCard>
  );
}
