"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SiteHeader, StoryCard } from "@/components/public-site";
import type { FeedPageData } from "@/lib/public-api";

type Interest = { target_type: string; target_id: string; weight: number };
type InterestOption = { target_type: string; target_id: string; name: string };

function cookie(name: string) {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

export function PersonalizedFeed({
  kind,
  cursor,
  language = "en",
}: {
  kind: "for-you" | "following";
  cursor?: string;
  language?: string;
}) {
  const [data, setData] = useState<FeedPageData | null>(null);
  const [interests, setInterests] = useState<Interest[]>([]);
  const [interestOptions, setInterestOptions] = useState<InterestOption[]>([]);
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState<
    "loading" | "ready" | "signed-out" | "error"
  >("loading");

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ language, limit: "12" });
    if (cursor) query.set("cursor", cursor);
    fetch(`/api/v1/portals/texas/feeds/${kind}?${query}`, {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) {
          setStatus("signed-out");
          return;
        }
        if (!response.ok) throw new Error("feed failed");
        const page = (await response.json()) as FeedPageData;
        setData(page);
        setStatus("ready");
        if (kind === "for-you") {
          const interestResponse = await fetch(
            "/api/v1/portals/texas/recommendations/me/interests",
            { credentials: "same-origin", signal: controller.signal },
          );
          if (interestResponse.ok) {
            setInterests(
              ((await interestResponse.json()) as { items: Interest[] }).items,
            );
          }
          const catalogResponse = await fetch(
            "/api/v1/portals/texas/recommendations/me/interest-catalog",
            { credentials: "same-origin", signal: controller.signal },
          );
          if (catalogResponse.ok) {
            setInterestOptions(
              ((await catalogResponse.json()) as { items: InterestOption[] })
                .items,
            );
          }
        }
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setStatus("error");
      });
    return () => controller.abort();
  }, [cursor, kind, language, revision]);

  async function toggleCategory(targetId: string, active: boolean) {
    const retained = interests.filter(
      (item) =>
        !(item.target_type === "category" && item.target_id === targetId),
    );
    const items = active
      ? [
          ...retained,
          { target_type: "category", target_id: targetId, weight: 3 },
        ]
      : retained;
    const csrf = cookie("news_csrf");
    const response = await fetch(
      "/api/v1/portals/texas/recommendations/me/interests",
      {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
        },
        body: JSON.stringify({ items }),
      },
    );
    if (!response.ok) return setStatus("error");
    setInterests(((await response.json()) as { items: Interest[] }).items);
    setStatus("loading");
    setRevision((value) => value + 1);
  }

  if (status === "loading")
    return (
      <main className="page-width personalized-state">Loading your feed…</main>
    );
  if (status === "signed-out") {
    return (
      <main className="page-width personalized-state">
        <h1>Sign in to personalize your Texas news</h1>
        <p>Open any story to log in or create an account, then return here.</p>
        <Link href="/latest">Browse the latest stories</Link>
      </main>
    );
  }
  if (status === "error" || !data) {
    return (
      <main className="page-width personalized-state">
        Your personalized feed is temporarily unavailable.
      </main>
    );
  }

  return (
    <>
      <SiteHeader
        portal={data.portal}
        language={data.language}
        alternates={data.alternates}
      />
      <main className="page-width listing-page personalized-page">
        <div className="page-kicker">Personalized Texas</div>
        <h1>{data.label}</h1>
        <p className="page-deck">
          {kind === "for-you"
            ? "A deterministic mix shaped by your interests, activity, and follows."
            : "The newest public stories about the topics, places, and people you follow."}
        </p>
        {kind === "for-you" ? (
          <fieldset className="interest-picker">
            <legend>Tune your category interests</legend>
            {interestOptions.map((option) => (
              <label key={option.target_id}>
                <input
                  type="checkbox"
                  checked={interests.some(
                    (item) =>
                      item.target_type === option.target_type &&
                      item.target_id === option.target_id,
                  )}
                  onChange={(event) =>
                    void toggleCategory(option.target_id, event.target.checked)
                  }
                />
                {option.name}
              </label>
            ))}
            <small>
              Entity, topic, and place interests are also learned from follows
              and activity.
            </small>
          </fieldset>
        ) : null}
        {data.items.length ? (
          <div className="listing-grid">
            {data.items.map((story) => (
              <StoryCard story={story} key={story.id} />
            ))}
          </div>
        ) : (
          <p className="quiet-copy">
            {kind === "following"
              ? "Follow an entity on a story to fill this feed."
              : "Published stories will appear here as they arrive."}
          </p>
        )}
        {data.next_cursor ? (
          <nav className="pagination" aria-label={`${data.label} feed pages`}>
            <span />
            <Link
              href={`${language === data.portal.default_language ? "" : `/${language}`}/${kind}?cursor=${encodeURIComponent(data.next_cursor)}`}
            >
              Older →
            </Link>
          </nav>
        ) : null}
      </main>
    </>
  );
}
