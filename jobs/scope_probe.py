"""One-off probe (not part of the pipeline): checks the real per-venue paper
counts for a hand-picked list of well-known AI / database / data-mining
venues, since profile_dblp.py's DATA-6 table only prints the top 50 venues
by raw volume, and none of these prestige venues are big enough by raw
paper count to make that cut (mega-journals and signal-processing/robotics
confs dominate by volume). This exists to make an evidence-based, thematically
coherent DATA_SCOPE choice instead of accepting the greedy by-volume default.
"""

from __future__ import annotations

from pathlib import Path

from profile_dblp import profile

CANDIDATES = [
    # AI / ML / NLP / CV
    "conf/aaai", "conf/ijcai", "conf/nips", "conf/icml", "conf/iclr",
    "conf/uai", "conf/aistats", "conf/cvpr", "conf/iccv", "conf/eccv",
    "conf/acl", "conf/emnlp", "conf/naacl", "journals/pami", "journals/jmlr",
    "journals/ai", "journals/artint", "journals/jair", "conf/ijcnn",
    "conf/aoi",
    # Databases
    "conf/sigmod", "conf/vldb", "conf/icde", "conf/pods", "conf/edbt",
    "journals/tods", "journals/pvldb", "journals/vldb", "journals/tkde",
    "conf/dasfaa",
    # Data mining / IR / web
    "conf/kdd", "conf/icdm", "conf/sdm", "conf/pakdd", "conf/pkdd",
    "conf/cikm", "conf/wsdm", "conf/www", "journals/kais", "conf/sigir",
]


def main():
    xml = Path("/data/dblp.xml.gz")
    dtd = Path("/data/dblp.dtd")
    stats = profile(xml, dtd)

    print(f"{'venue':<20} {'total':>10}  {'>=2000':>10}  {'>=2010':>10}  {'>=2015':>10}")
    total_all, total_2000, total_2010, total_2015 = 0, 0, 0, 0
    for v in CANDIDATES:
        yc = stats.venue_year_counts.get(v)
        if not yc:
            print(f"{v:<20} {'(not found)':>10}")
            continue
        t_all = sum(yc.values())
        t_2000 = sum(c for y, c in yc.items() if y >= 2000)
        t_2010 = sum(c for y, c in yc.items() if y >= 2010)
        t_2015 = sum(c for y, c in yc.items() if y >= 2015)
        total_all += t_all
        total_2000 += t_2000
        total_2010 += t_2010
        total_2015 += t_2015
        print(f"{v:<20} {t_all:>10,}  {t_2000:>10,}  {t_2010:>10,}  {t_2015:>10,}")

    print(f"\n{'TOTAL':<20} {total_all:>10,}  {total_2000:>10,}  {total_2010:>10,}  {total_2015:>10,}")


if __name__ == "__main__":
    main()
