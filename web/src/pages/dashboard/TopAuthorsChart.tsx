import type { EChartsOption } from "echarts";
import { useNavigate } from "react-router-dom";

import ChartCard from "../../components/ChartCard";
import { accentColor } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { useChart } from "../../lib/useChart";

interface AuthorRow {
  author_id: number;
  name: string;
  paper_count: number;
}

export default function TopAuthorsChart() {
  const navigate = useNavigate();
  const state = useApi<AuthorRow[]>("/api/dashboard/top-authors?limit=15", (d) => d.length === 0);
  const rows = state.status === "ready" ? [...state.data].reverse() : [];

  const option: EChartsOption | null =
    rows.length > 0
      ? {
          tooltip: { trigger: "axis", valueFormatter: (v) => `${v} papers` },
          grid: { left: 160, right: 24, top: 12, bottom: 24 },
          xAxis: { type: "value", name: "Papers" },
          yAxis: { type: "category", data: rows.map((r) => r.name) },
          series: [{ type: "bar", data: rows.map((r) => r.paper_count), color: accentColor() }],
        }
      : null;
  const chartRef = useChart(option, {
    click: (params) => {
      const row = rows[params.dataIndex];
      if (row) navigate(`/author/${row.author_id}`);
    },
  });

  const top = state.status === "ready" ? state.data[0] : null;
  const subtitle = top ? `${top.name} leads with ${top.paper_count.toLocaleString()} papers - click a bar to open an author` : undefined;

  return (
    <ChartCard title="Top 15 authors by paper count" subtitle={subtitle} state={state}>
      {() => <div ref={chartRef} className="chart-canvas" />}
    </ChartCard>
  );
}
