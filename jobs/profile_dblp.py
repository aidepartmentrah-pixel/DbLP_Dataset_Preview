"""Task 0: profile the real dblp XML dump before writing any ETL code.

Covers DATA-1 through DATA-6 from the Technical Proposal §8.0:
  DATA-1  stream-parse with the real DTD (constant memory)
  DATA-2  record counts per type and per year
  DATA-3  field completeness (author, year, ee, crossref, ORCID)
  DATA-4  authors-per-paper / papers-per-author distributions, top-50 venues
  DATA-5  author disambiguation (ORCID coverage, homonym-suffix check)
  DATA-6  a suggested DATA_SCOPE (venue list + start year) sized at 300k-800k papers

Run inside the `jobs` container, e.g.:
    python profile_dblp.py --xml /data/dblp.xml.gz --dtd /data/dblp.dtd --out /app/reports/dblp_profile.md
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from dblp_xml import author_key as _author_key
from dblp_xml import element_text as _element_text
from dblp_xml import stream_records
from dblp_xml import venue_prefix as _venue_prefix

HOMONYM_SUFFIX_RE = re.compile(r"^(.*) (\d{4})$")


@dataclass
class ProfileStats:
    type_counts: Counter = field(default_factory=Counter)
    year_counts: Counter = field(default_factory=Counter)
    venue_prefix_counts: Counter = field(default_factory=Counter)

    field_present: Counter = field(default_factory=Counter)  # author/year/ee/crossref
    publication_total: int = 0

    authors_per_paper: Counter = field(default_factory=Counter)  # count -> num papers
    papers_per_author: dict = field(default_factory=lambda: defaultdict(int))

    author_tag_total: int = 0
    author_tag_with_orcid: int = 0
    homonym_suffix_names: Counter = field(default_factory=Counter)  # base name -> distinct suffixed variants

    www_total: int = 0
    www_alias_counts: Counter = field(default_factory=Counter)  # num aliases -> num www records

    # venue -> (min year seen, max year seen, count), used for the DATA-6 suggestion
    venue_year_counts: dict = field(default_factory=lambda: defaultdict(Counter))


def profile(xml_gz_path: Path, dtd_path: Path, limit: int | None = None) -> ProfileStats:
    stats = ProfileStats()

    for elem in stream_records(xml_gz_path, dtd_path, limit=limit):
        tag = elem.tag
        stats.type_counts[tag] += 1

        if tag == "www":
            # Person records: no venue, contribute only to alias/pid stats (DATA-5).
            author_elems = elem.findall("author")
            stats.www_total += 1
            stats.www_alias_counts[len(author_elems)] += 1
            for a in author_elems:
                stats.author_tag_total += 1
                if a.get("orcid"):
                    stats.author_tag_with_orcid += 1
            continue

        key = elem.get("key", "")
        if key:
            stats.venue_prefix_counts[_venue_prefix(key)] += 1

        year_text = elem.findtext("year")
        year = None
        if year_text and year_text.strip().isdigit():
            year = int(year_text.strip())
            stats.year_counts[year] += 1

        if tag == "proceedings":
            # A venue/container record, not an authored work: counted above
            # for DATA-2/DATA-4 (type, year, venue overview) but deliberately
            # excluded from DATA-3/DATA-4's author-side stats below, so it
            # doesn't drag down "% records with an author" or inflate the
            # DATA-6 paper-count estimate with non-papers.
            continue

        # Authored publication record (DATA-3, DATA-4, DATA-5)
        author_elems = elem.findall("author")
        stats.publication_total += 1
        if author_elems:
            stats.field_present["author"] += 1
        if year_text:
            stats.field_present["year"] += 1
        if elem.findtext("ee"):
            stats.field_present["ee"] += 1
        if elem.get("crossref") or elem.findtext("crossref"):
            stats.field_present["crossref"] += 1

        if key:
            stats.venue_year_counts[_venue_prefix(key)][year or 0] += 1

        stats.authors_per_paper[len(author_elems)] += 1

        for a in author_elems:
            stats.author_tag_total += 1
            if a.get("orcid"):
                stats.author_tag_with_orcid += 1
            akey = _author_key(a)
            stats.papers_per_author[akey] += 1

            name_text = _element_text(a)
            m = HOMONYM_SUFFIX_RE.match(name_text)
            if m:
                stats.homonym_suffix_names[m.group(1)] += 1

    return stats


def _percentiles(counter: Counter, points=(50, 90, 99)) -> dict:
    """counter: value -> frequency. Returns percentile -> value."""
    total = sum(counter.values())
    if total == 0:
        return {p: 0 for p in points}
    sorted_items = sorted(counter.items())
    out = {}
    for p in points:
        target = total * p / 100
        cum = 0
        chosen = sorted_items[-1][0]
        for value, freq in sorted_items:
            cum += freq
            if cum >= target:
                chosen = value
                break
        out[p] = chosen
    return out


# Catch-all buckets that show up as huge "venue" prefixes in the real dump
# but aren't curated venues: journals/corr is dblp's indexing of arXiv CS
# preprints (no peer review), and phd/* prefixes are PhD-thesis-repository
# aggregators (basesearch, dnb, hal, ethos), not conferences/journals.
# Confirmed by inspecting the real top-50 list, not assumed up front.
_NON_VENUE_EXACT = {"journals/corr"}
_NON_VENUE_PREFIX_STARTS = ("phd/",)


def _is_real_venue(prefix: str) -> bool:
    if prefix in _NON_VENUE_EXACT:
        return False
    return not any(prefix.startswith(p) for p in _NON_VENUE_PREFIX_STARTS)


def suggest_data_scope(stats: ProfileStats, target_min=300_000, target_max=800_000) -> dict:
    """DATA-6: pick a start year + a curated, multi-venue list landing in
    [target_min, target_max] real papers, by ranking real venues (excluding
    the catch-all non-venue prefixes above) by paper count and taking as
    many of the largest as fit under target_max - not stopping at the first
    single venue that alone clears target_min, which would (and initially
    did) hand back a "scope" of just one arXiv-sized bucket."""
    best = None
    for start_year in (2000, 2005, 2010, 2012, 2015, 2018):
        venue_totals = Counter()
        for venue, year_counter in stats.venue_year_counts.items():
            if not _is_real_venue(venue):
                continue
            total = sum(c for yr, c in year_counter.items() if yr >= start_year)
            if total > 0:
                venue_totals[venue] = total

        ranked = venue_totals.most_common()
        cumulative = 0
        chosen_venues = []
        for venue, count in ranked:
            if chosen_venues and cumulative + count > target_max:
                break
            cumulative += count
            chosen_venues.append(venue)
            if cumulative >= target_max:
                break

        candidate = {
            "start_year": start_year,
            "total_papers": cumulative,
            "num_venues": len(chosen_venues),
            "venues": chosen_venues,
        }
        if target_min <= cumulative <= target_max:
            return candidate
        if best is None or abs(cumulative - (target_min + target_max) / 2) < abs(
            best["total_papers"] - (target_min + target_max) / 2
        ):
            best = candidate
    return best


def render_markdown(stats: ProfileStats, scope_suggestion: dict) -> str:
    lines = []
    lines.append("# dblp dataset profile\n")
    lines.append(f"Total records streamed: **{sum(stats.type_counts.values()):,}**\n")

    lines.append("\n## DATA-2: records per type\n")
    lines.append("| Type | Count |\n|---|---|")
    for tag, count in stats.type_counts.most_common():
        lines.append(f"| {tag} | {count:,} |")

    lines.append("\n## DATA-2: records per year (publications only)\n")
    lines.append("| Year | Count |\n|---|---|")
    for year, count in sorted(stats.year_counts.items()):
        lines.append(f"| {year} | {count:,} |")

    lines.append("\n## DATA-3: field completeness (publication records only)\n")
    lines.append(f"Publication records total: **{stats.publication_total:,}**\n")
    lines.append("| Field | Present | Share |\n|---|---|---|")
    for f in ("author", "year", "ee", "crossref"):
        present = stats.field_present.get(f, 0)
        share = present / stats.publication_total * 100 if stats.publication_total else 0
        lines.append(f"| {f} | {present:,} | {share:.1f}% |")
    orcid_share = (
        stats.author_tag_with_orcid / stats.author_tag_total * 100 if stats.author_tag_total else 0
    )
    lines.append(
        f"| author `orcid` attribute | {stats.author_tag_with_orcid:,} of {stats.author_tag_total:,} author tags | {orcid_share:.1f}% |"
    )

    lines.append("\n## DATA-4: authors per paper\n")
    app_pct = _percentiles(stats.authors_per_paper)
    total_papers_with_authors = sum(stats.authors_per_paper.values())
    mean_authors = (
        sum(k * v for k, v in stats.authors_per_paper.items()) / total_papers_with_authors
        if total_papers_with_authors
        else 0
    )
    lines.append(f"- Mean: {mean_authors:.2f}")
    lines.append(f"- Median (p50): {app_pct[50]}, p90: {app_pct[90]}, p99: {app_pct[99]}")

    lines.append("\n## DATA-4: papers per author\n")
    paper_count_freq = Counter(stats.papers_per_author.values())
    ppa_pct = _percentiles(paper_count_freq)
    total_authors = len(stats.papers_per_author)
    mean_papers = sum(stats.papers_per_author.values()) / total_authors if total_authors else 0
    lines.append(f"- Distinct authors seen: {total_authors:,}")
    lines.append(f"- Mean papers/author: {mean_papers:.2f}")
    lines.append(f"- Median (p50): {ppa_pct[50]}, p90: {ppa_pct[90]}, p99: {ppa_pct[99]}")

    lines.append("\n## DATA-4: top 50 venue key prefixes\n")
    lines.append("| Venue prefix | Count |\n|---|---|")
    for venue, count in stats.venue_prefix_counts.most_common(50):
        lines.append(f"| {venue} | {count:,} |")

    lines.append("\n## DATA-5: author disambiguation\n")
    lines.append(f"- `www` (person) records: {stats.www_total:,}")
    multi_alias = sum(c for n, c in stats.www_alias_counts.items() if n > 1)
    lines.append(f"- `www` records with more than one listed name/alias: {multi_alias:,}")
    homonym_bases = sum(1 for v in stats.homonym_suffix_names.values() if v >= 1)
    lines.append(
        f"- Distinct base names carrying a numeric disambiguation suffix (e.g. \"Wei Wang 0001\"): {homonym_bases:,}"
    )
    lines.append(f"- Author-tag `orcid` coverage: {orcid_share:.1f}% (see DATA-3 table above)")

    lines.append("\n## DATA-6: suggested v1 DATA_SCOPE\n")
    lines.append(f"- Suggested start year: **{scope_suggestion['start_year']}**")
    lines.append(f"- Suggested venue count: **{scope_suggestion['num_venues']}**")
    lines.append(f"- Estimated papers in scope: **{scope_suggestion['total_papers']:,}**")
    lines.append("- Venue list (top of the ranked list, by paper count):")
    for v in scope_suggestion["venues"][:30]:
        lines.append(f"  - {v}")
    if len(scope_suggestion["venues"]) > 30:
        lines.append(f"  - ...and {len(scope_suggestion['venues']) - 30} more")

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", type=Path, default=Path("/data/dblp.xml.gz"))
    ap.add_argument("--dtd", type=Path, default=Path("/data/dblp.dtd"))
    ap.add_argument("--out", type=Path, default=Path("/app/reports/dblp_profile.md"))
    ap.add_argument("--limit", type=int, default=None, help="cap records read (for dev testing)")
    args = ap.parse_args()

    stats = profile(args.xml, args.dtd, limit=args.limit)
    scope = suggest_data_scope(stats)
    report = render_markdown(stats, scope)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out} ({len(report):,} bytes)")


if __name__ == "__main__":
    main()
