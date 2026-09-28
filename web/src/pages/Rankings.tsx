import { useState } from "react";

import AboutMeasures from "./rankings/AboutMeasures";
import InfluenceBridgeScatter from "./rankings/InfluenceBridgeScatter";
import RankingsTable from "./rankings/RankingsTable";

export default function Rankings() {
  const [venue, setVenue] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");

  return (
    <div className="dashboard-grid">
      <div className="card chart-card span-12 filter-row">
        <label>
          Venue prefix
          <input value={venue} onChange={(e) => setVenue(e.target.value)} placeholder="e.g. conf/kdd" />
        </label>
        <label>
          From year
          <input value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} placeholder="2010" />
        </label>
        <label>
          To year
          <input value={yearTo} onChange={(e) => setYearTo(e.target.value)} placeholder="2026" />
        </label>
      </div>

      <RankingsTable sort="pagerank" title="Top 50 by PageRank" venue={venue} yearFrom={yearFrom} yearTo={yearTo} />
      <RankingsTable sort="betweenness" title="Top 50 by betweenness" venue={venue} yearFrom={yearFrom} yearTo={yearTo} />
      <InfluenceBridgeScatter />
      <AboutMeasures />
    </div>
  );
}
