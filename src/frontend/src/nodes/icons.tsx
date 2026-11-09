// Section icons as inline SVG (font glyphs and emoji render as boxes on machines without them).
const PATHS: Record<string, string> = {
  profile: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 10.5v6M12 7.5v.01",
  leaders: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20a7.5 7.5 0 0 1 15 0",
  holders: "M12 3v9h9A9 9 0 1 1 12 3zM15 3.5A9 9 0 0 1 20.5 9H15z",
  investments: "M12 4v5M12 9H6v4M12 9h6v4M4 13h4v6H4zM10 13h4v6h-4zM16 13h4v6h-4z",
  price: "M3 17l6-6 4 4 8-8M15 7h6v6",
  reports: "M6 3h9l4 4v14H6zM15 3v4h4M9 11h7M9 15h7M9 19h4",
  metrics: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  trading: "M4 8h14l-4-4M20 16H6l4 4",
  related: "M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1",
  news: "M4 5h13v14H6a2 2 0 0 1-2-2zM17 9h3v8a2 2 0 0 1-2 2M7 9h7M7 13h7M7 16h4",
};

export function SectionIcon({ category }: { category: string }) {
  return (
    <svg className="section-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[category] ?? PATHS.profile} />
    </svg>
  );
}
