import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryView, HomeView, StoryView } from "@/components/public-site";
import type { Homepage, Portal, Story, StorySummary } from "@/lib/public-api";

const portal: Portal = {
  name: "Texas Entertainment Daily",
  slug: "texas",
  domain: "texas.example",
  timezone: "America/Chicago",
  default_language: "en",
  canonical_url: "https://texas.example",
  branding: {},
  categories: [
    { name: "Sports", slug: "sports" },
    { name: "Music", slug: "music" },
  ],
};

const summary: StorySummary = {
  id: "00000000-0000-0000-0000-000000000001",
  slug: "austin-music",
  url: "/story/austin-music",
  canonical_url: "https://texas.example/story/austin-music",
  content_type: "article",
  title: "Austin music takes center stage",
  subtitle: "A Texas original",
  description: "Artists from across Texas meet in Austin.",
  author: "Newsroom",
  published_at: "2026-09-05T12:00:00Z",
  updated_at: "2026-09-05T12:00:00Z",
  source: { name: "Texas Wire", url: "https://wire.example" },
  categories: [{ name: "Music", slug: "music" }],
  geography: [{ name: "Austin", slug: "austin", type: "city" }],
  media: [],
};

describe("Home", () => {
  it("renders the public hero, navigation, trending and category sections", () => {
    const data: Homepage = {
      portal,
      hero: summary,
      trending: [{ ...summary, id: "2", title: "Texas tour announced" }],
      category_sections: [
        { category: { name: "Music", slug: "music" }, items: [summary] },
      ],
      video_highlights: [],
    };
    render(<HomeView data={data} />);

    expect(
      screen.getByRole("heading", {
        name: "Austin music takes center stage",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Trending in Texas" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Music" }).length,
    ).toBeGreaterThan(0);
  });

  it("renders a calm empty newsroom when no content is published", () => {
    render(
      <HomeView
        data={{
          portal,
          hero: null,
          trending: [],
          category_sections: [],
          video_highlights: [],
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Texas stories are on the way" }),
    ).toBeInTheDocument();
  });
});

describe("public detail pages", () => {
  it("renders category content and pagination", () => {
    render(
      <CategoryView
        data={{
          portal,
          feed: "category",
          scope: "music",
          label: "Music",
          language: "en",
          canonical_url: "https://texas.example/music",
          items: [summary],
          next_cursor: "opaque-cursor",
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Music", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Older →" })).toHaveAttribute(
      "href",
      "/music?cursor=opaque-cursor",
    );
  });

  it("renders story body, source, taxonomy, share controls and related content", () => {
    const story: Story = {
      ...summary,
      portal,
      body: "Opening paragraph.\n\nSecond paragraph.",
      original_url: "https://wire.example/austin-music",
      entities: [{ name: "Austin Band", slug: "austin-band", type: "artist" }],
      seo: {},
      related: [{ ...summary, id: "3", title: "More live music" }],
    };
    render(<StoryView story={story} portal={portal} />);
    expect(screen.getByText("Opening paragraph.")).toBeInTheDocument();
    expect(screen.getByText("Source: Texas Wire")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Share this story" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Austin Band")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Related stories" }),
    ).toBeInTheDocument();
  });
});
