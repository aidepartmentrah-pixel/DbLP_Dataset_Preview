export default function AboutMeasures() {
  return (
    <div className="card chart-card span-12">
      <h3 className="chart-title">About these measures</h3>
      <p>
        <strong>PageRank</strong> asks who is <em>influential</em>: a random walker who follows
        co-authorship links spends more time at well-connected authors. (Brin &amp; Page, 1998)
      </p>
      <p>
        <strong>Betweenness</strong> asks who is a <em>bridge</em>: authors who sit on many
        shortest paths between other authors, connecting otherwise separate research groups.
        (Freeman, 1977)
      </p>
    </div>
  );
}
