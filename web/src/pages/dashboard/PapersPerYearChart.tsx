import type { EChartsOption } from "echarts";

import ChartCard from "../../components/ChartCard";
import { conferenceColor, journalColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface YearRow {
  year: number;
  journal: number;
  conference: number;
  other: number;
}

export default function PapersPerYearChart() {
  const state = useApi<YearRow[]>("/api/dashboard/papers-per-year", (d) => d.length === 0);
  const rows = state.status === "ready" ? state.data : [];

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: { trigger: "axis", valueFormatter: (v) => `${v} papers` },
          grid: { left: 48, right: 24, top: 24, bottom: 32 },
          xAxis: { type: "category", data: rows.map((r) => r.year) },
          yAxis: { type: "value", name: "Papers" },
          series: [
            {
              name: "Journal", type: "line", data: rows.map((r) => r.journal),
              color: journalColor(), showSymbol: false, endLabel: { show: true, formatter: "Journal" },
            },
            {
              name: "Conference", type: "line", data: rows.map((r) => r.conference),
              color: conferenceColor(), showSymbol: false, endLabel: { show: true, formatter: "Conference" },
            },
          ],
        }
      : null;
  const chartRef = useChart(option);

  const totalJournal = rows.reduce((s, r) => s + r.journal, 0);
  const totalConference = rows.reduce((s, r) => s + r.conference, 0);
  const subtitle =
    rows.length === 0
      ? undefined
      : totalConference > totalJournal
        ? `Conferences lead journals ${(totalConference / (totalJournal || 1)).toFixed(1)}:1 in this scope`
        : `Journals lead conferences ${(totalJournal / (totalConference || 1)).toFixed(1)}:1 in this scope`;

  return (
    <ChartCard title="Publications per year" subtitle={subtitle} state={state}>
      {() => <div ref={chartRef} className="chart-canvas" />}
    </ChartCard>
  );
}
