import KpiTiles from "./dashboard/KpiTiles";
import PapersPerYearChart from "./dashboard/PapersPerYearChart";
import ProductivityChart from "./dashboard/ProductivityChart";
import TeamSizeChart from "./dashboard/TeamSizeChart";
import TopAuthorsChart from "./dashboard/TopAuthorsChart";
import TopicTrendsHeatmap from "./dashboard/TopicTrendsHeatmap";
import TopVenuesChart from "./dashboard/TopVenuesChart";

export default function Dashboard() {
  return (
    <div className="dashboard-grid">
      <KpiTiles />
      <PapersPerYearChart />
      <TopVenuesChart />
      <TopAuthorsChart />
      <TeamSizeChart />
      <ProductivityChart />
      <TopicTrendsHeatmap />
    </div>
  );
}
