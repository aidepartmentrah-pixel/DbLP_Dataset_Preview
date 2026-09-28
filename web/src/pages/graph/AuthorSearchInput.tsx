import { useEffect, useState } from "react";

interface AuthorHit {
  author_id: number;
  name: string;
}

export default function AuthorSearchInput({
  placeholder,
  onSelect,
}: {
  placeholder: string;
  onSelect: (author: AuthorHit) => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<AuthorHit[]>([]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      fetch(`/api/graph/search-author?q=${encodeURIComponent(query)}`)
        .then((r) => r.json())
        .then((data) => {
          if (!cancelled) setHits(data);
        })
        .catch(() => {});
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  return (
    <div className="author-search">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
      />
      {hits.length > 0 && (
        <ul className="author-search-results">
          {hits.map((hit) => (
            <li
              key={hit.author_id}
              onClick={() => {
                onSelect(hit);
                setQuery(hit.name);
                setHits([]);
              }}
            >
              {hit.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
