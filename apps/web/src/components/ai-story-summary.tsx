"use client";

import { useState } from "react";

type Summary = {
  bullets: string[];
  generated: boolean;
  fallback_used: boolean;
  cached: boolean;
  sources: { title: string; canonical_url: string }[];
};

export function AiStorySummary({
  storySlug,
  language,
}: {
  storySlug: string;
  language: string;
}) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  async function load() {
    setState("loading");
    try {
      const query = new URLSearchParams({ language });
      const response = await fetch(
        `/api/v1/portals/texas/stories/${encodeURIComponent(storySlug)}/ai-summary?${query}`,
        { headers: { Accept: "application/json" }, cache: "no-store" },
      );
      if (!response.ok) throw new Error("summary unavailable");
      setSummary((await response.json()) as Summary);
      setState("idle");
    } catch {
      setState("error");
    }
  }

  return (
    <section className="ai-summary" aria-labelledby="ai-summary-title">
      <div>
        <span className="page-kicker">AI service</span>
        <h2 id="ai-summary-title">Story in brief</h2>
      </div>
      {summary ? (
        <>
          <ul>
            {summary.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
          <p>
            {summary.generated
              ? "AI-generated from this published story only."
              : "Deterministic fallback from this published story only."}{" "}
            Verify details in the full article.
          </p>
        </>
      ) : (
        <>
          <p>Generate a short, source-bound summary on demand.</p>
          <button type="button" disabled={state === "loading"} onClick={load}>
            {state === "loading" ? "Summarizing…" : "Summarize this story"}
          </button>
          {state === "error" ? (
            <p role="alert">The summary is temporarily unavailable.</p>
          ) : null}
        </>
      )}
    </section>
  );
}
