import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PersonalizedFeed } from "@/components/personalized-feed";

const portal = {
  name: "Texas Entertainment Daily",
  slug: "texas",
  domain: "texas.example",
  timezone: "America/Chicago",
  default_language: "en",
  supported_languages: ["en", "es"],
  canonical_url: "https://texas.example",
  branding: {},
  categories: [{ name: "Music", slug: "music" }],
};

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("PersonalizedFeed", () => {
  it("requires sign-in without exposing private feed data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => response({}, 401)),
    );
    render(<PersonalizedFeed kind="following" />);
    expect(
      await screen.findByRole("heading", {
        name: "Sign in to personalize your Texas news",
      }),
    ).toBeInTheDocument();
  });

  it("renders For You stories and the private interest catalog", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementationOnce(() =>
          response({
            portal,
            feed: "for_you",
            scope: null,
            label: "For You",
            language: "en",
            canonical_url: "https://texas.example/for-you",
            alternates: {
              en: "https://texas.example/for-you",
              es: "https://texas.example/es/for-you",
            },
            items: [
              {
                id: "1",
                slug: "recommended",
                url: "/story/recommended",
                canonical_url: "https://texas.example/story/recommended",
                language: "en",
                alternates: {
                  en: "https://texas.example/story/recommended",
                },
                content_type: "article",
                title: "Recommended in Texas",
                subtitle: null,
                description: "A recommendation",
                author: null,
                published_at: "2026-09-09T12:00:00Z",
                updated_at: "2026-09-09T12:00:00Z",
                source: null,
                categories: [{ name: "Music", slug: "music" }],
                geography: [],
                media: [],
              },
            ],
            next_cursor: null,
          }),
        )
        .mockImplementationOnce(() => response({ items: [] }))
        .mockImplementationOnce(() =>
          response({
            items: [
              {
                target_type: "category",
                target_id: "00000000-0000-0000-0000-000000000001",
                name: "Music",
              },
            ],
          }),
        ),
    );
    render(<PersonalizedFeed kind="for-you" />);
    expect(await screen.findByText("Recommended in Texas")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("Music")).toBeInTheDocument(),
    );
  });
});
