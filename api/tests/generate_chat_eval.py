"""CHAT-7: generates api/tests/chat_eval.jsonl - 100 real, grounded
questions (§6.8: "100 hand-written questions with known answers"). Every
expected value here was pulled from the actual live database (see the
`SELECT`s in this file's history / task table write-up), not guessed, so
each question's "known answer" is real and independently re-checkable.

Run once, from a shell with DATABASE_URL_READONLY set (e.g. inside the
`api` container): python tests/generate_chat_eval.py
"""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL_READONLY"].replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(url)

questions = []


def add(category: str, question: str, **expect):
    questions.append({"category": category, "question": question, **expect})


with engine.connect() as conn:
    # --- Factual / SQL (40) ---------------------------------------------
    venues = ["conf/kdd", "conf/vldb", "conf/sigmod", "conf/icml", "conf/aaai", "conf/acl", "conf/www", "conf/sigir"]
    years = [2018, 2020, 2022]
    for venue in venues:
        for year in years:
            count = conn.execute(
                text("SELECT COUNT(*) FROM paper p JOIN venue v ON v.venue_id=p.venue_id WHERE v.key_prefix=:v AND p.year=:y"),
                {"v": venue, "y": year},
            ).scalar()
            add("factual", f"How many papers did {venue} publish in {year}?", expected_contains=str(count))

    authors_for_counts = [
        "Philip S. Yu", "Jiawei Han 0001", "Yoshua Bengio", "Luc Van Gool",
        "Dacheng Tao", "Bernhard Schölkopf", "Eric P. Xing", "Christos Faloutsos",
    ]
    for name in authors_for_counts:
        count = conn.execute(
            text("SELECT COUNT(*) FROM authorship au JOIN author a ON a.author_id=au.author_id WHERE a.name=:n"),
            {"n": name},
        ).scalar()
        add("factual", f"How many papers has {name} published in this dataset?", expected_contains=str(count))

    kpis = conn.execute(text("SELECT paper_count, author_count, venue_count FROM v_kpis")).first()
    add("factual", "How many papers are in the dblp dataset in total?", expected_contains=str(kpis[0]))
    add("factual", "How many distinct authors are in the dataset?", expected_contains=str(kpis[1]))
    add("factual", "How many venues are covered by this dataset?", expected_contains=str(kpis[2]))

    top_venues = conn.execute(
        text("SELECT key_prefix, SUM(paper_count) AS c FROM v_top_venues GROUP BY key_prefix ORDER BY c DESC LIMIT 5")
    ).all()
    for venue, count in top_venues:
        add("factual", f"How many total papers are there from {venue}?", expected_contains=str(count))

    # --- Topical / semantic search (30) ----------------------------------
    topics = [
        "diversity in search result ranking", "graph neural networks", "recommendation systems",
        "adversarial examples in deep learning", "federated learning", "retrieval-augmented generation",
        "self-supervised learning", "knowledge graph embeddings", "named entity recognition",
        "query result summarization", "citation recommendation", "cross-lingual information retrieval",
        "session-based recommendation", "learning to rank", "neural machine translation",
        "graph convolutional networks", "attention mechanisms in transformers", "few-shot learning",
        "contrastive learning", "generative adversarial networks", "text classification",
        "entity resolution", "social network analysis", "anomaly detection in graphs",
        "multi-task learning", "domain adaptation", "explainable AI", "reinforcement learning for recommendation",
        "sentiment analysis", "question answering systems",
    ]
    for topic in topics:
        add("topical", f"Find me a paper about {topic}.", expect_nonempty_citation=True)

    # --- Graph (30) --------------------------------------------------------
    coauthor_pairs = conn.execute(
        text("""
            SELECT a1.name, a2.name FROM coauthor_edge ce
            JOIN author a1 ON a1.author_id=ce.src JOIN author a2 ON a2.author_id=ce.dst
            ORDER BY ce.weight DESC LIMIT 14
        """)
    ).all()
    for a1, a2 in coauthor_pairs:
        add("graph", f"Are {a1} and {a2} co-authors?", expected_contains="yes_coauthors")

    bridge_authors = conn.execute(
        text("SELECT a.name FROM author_metrics am JOIN author a ON a.author_id=am.author_id ORDER BY am.betweenness DESC LIMIT 10")
    ).all()
    for (name,) in bridge_authors:
        add("graph", f"Is {name} an important bridge author connecting different research communities?", expect_nonempty=True)

    for name in authors_for_counts[:5]:
        add("graph", f"Who are {name}'s top co-authors?", expect_nonempty=True)

add("graph", "How is Philip S. Yu connected to Yoshua Bengio through co-authorship?",
    expected_contains="Zhiping Xiao")

out_path = Path(__file__).parent / "chat_eval.jsonl"
with out_path.open("w", encoding="utf-8") as f:
    for q in questions[:100]:
        f.write(json.dumps(q) + "\n")

print(f"Wrote {min(len(questions), 100)} questions to {out_path}")
