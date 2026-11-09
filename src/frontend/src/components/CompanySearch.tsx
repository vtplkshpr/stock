import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SearchHit } from "../types";

/** Ticker / name search with suggestions; companies holding data are listed first. */
export function CompanySearch({ onSelect, autoFocus, placeholder = "Search a ticker or company name…" }: {
  onSelect: (ticker: string) => void;
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const request = useRef(0);

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setHits([]);
      return;
    }
    const id = ++request.current;
    const timer = window.setTimeout(() => {
      api.search(text).then((found) => {
        if (id === request.current) {
          setHits(found);
          setActive(0);
        }
      }).catch(() => setHits([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  const choose = (hit: SearchHit | undefined) => {
    const ref = hit?.ref ?? query.trim().toUpperCase();
    if (!ref) return;
    onSelect(ref);
    setQuery("");
    setHits([]);
    setOpen(false);
  };

  return (
    <div className="company-search">
      <input
        type="search"
        value={query}
        autoFocus={autoFocus}
        placeholder={placeholder}
        aria-label="Search company"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, hits.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter") choose(hits[active]);
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && hits.length > 0 && (
        <ul className="search-results" role="listbox">
          {hits.map((hit, index) => (
            <li key={hit.ref} role="option" aria-selected={index === active}
                className={index === active ? "active" : ""}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(hit);
                }}>
              {hit.ticker ? <b>{hit.ticker}</b> : <span className="chip">Unlisted</span>}
              <span className="hit-name">{hit.company_name}</span>
              {hit.exchange && <span className="chip">{hit.exchange}</span>}
              {hit.has_data && <span className="chip chip-strong" title="Has detailed data">data</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
