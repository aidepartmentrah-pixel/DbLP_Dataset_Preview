import { useApi } from "../../lib/useApi";

interface Kpis {
  papers: number;
  authors: number;
  venues: number;
  last_update: string | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function KpiTiles() {
  const state = useApi<Kpis>("/api/dashboard/kpis");

  const tiles = [
    { label: "Papers", value: state.status === "ready" ? state.data.papers.toLocaleString() : "—" },
    { label: "Authors", value: state.status === "ready" ? state.data.authors.toLocaleString() : "—" },
    { label: "Venues", value: state.status === "ready" ? state.data.venues.toLocaleString() : "—" },
    { label: "Last update", value: state.status === "ready" ? formatDate(state.data.last_update) : "—" },
  ];

  return (
    <div className="kpi-row">
      {tiles.map((tile) => (
        <div className="card kpi-tile" key={tile.label}>
          <p className="kpi-label">{tile.label}</p>
          <p className="kpi-value">{tile.value}</p>
        </div>
      ))}
    </div>
  );
}
