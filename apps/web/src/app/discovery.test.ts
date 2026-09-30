import { beforeEach, describe, expect, it, vi } from "vitest";

const { portal, story, getHomepage, getPublicIndexPage } = vi.hoisted(() => {
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

  const story = {
    id: "00000000-0000-0000-0000-000000000001",
    slug: "austin-music",
    url: "/story/austin-music",
    canonical_url: "https://texas.example/story/austin-music",
    language: "en",
    alternates: {
      en: "https://texas.example/story/austin-music",
      es: "https://texas.example/es/story/austin-music",
    },
    content_type: "article",
    title: "Austin & music",
    subtitle: null,
    description: "Local <reporting>",
    author: "Ada Reporter",
    published_at: "2026-09-29T12:00:00Z",
    updated_at: "2026-09-29T13:00:00Z",
    source: null,
    categories: [{ name: "Music", slug: "music" }],
    geography: [{ name: "Austin", slug: "austin", type: "city" }],
    media: [],
  };

  const getHomepage = vi.fn(async (language = "en") => ({
    portal,
    language,
    canonical_url: `https://texas.example${language === "en" ? "" : "/es"}`,
    alternates: {},
    hero: null,
    trending: [],
    category_sections: [],
    video_highlights: [],
    media_highlights: [],
  }));
  const getPublicIndexPage = vi.fn(
    async (_cursor?: string, language = "en") => ({
      portal,
      feed: "latest",
      scope: null,
      label: "Latest",
      language,
      canonical_url: "https://texas.example/latest",
      alternates: {},
      items: [
        language === "en"
          ? story
          : {
              ...story,
              language: "es",
              url: "/es/story/austin-music",
              canonical_url: "https://texas.example/es/story/austin-music",
              title: "Música de Austin",
            },
      ],
      next_cursor: null as string | null,
    }),
  );
  return { portal, story, getHomepage, getPublicIndexPage };
});

vi.mock("@/lib/public-api", () => ({ getHomepage, getPublicIndexPage }));

import * as newsSitemap from "@/app/news-sitemap.xml/route";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { getAllPublicStories } from "@/lib/discovery";

describe("crawler discovery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-30T12:00:00Z"));
  });

  it("allows search crawlers while excluding private surfaces and GPT training", async () => {
    const value = await robots();
    expect(value.sitemap).toEqual([
      "https://texas.example/sitemap.xml",
      "https://texas.example/news-sitemap.xml",
    ]);
    expect(value.rules).toContainEqual(
      expect.objectContaining({ userAgent: "OAI-SearchBot", allow: "/" }),
    );
    expect(value.rules).toContainEqual({ userAgent: "GPTBot", disallow: "/" });
    expect(value.rules).toContainEqual(
      expect.objectContaining({
        userAgent: "*",
        disallow: expect.arrayContaining(["/admin/", "/for-you", "/search"]),
      }),
    );
  });

  it("builds localized canonical story and author entries from the public feed", async () => {
    const entries = await sitemap();
    expect(entries.map((entry) => entry.url)).toEqual(
      expect.arrayContaining([
        "https://texas.example/story/austin-music",
        "https://texas.example/es/story/austin-music",
        "https://texas.example/authors/Ada%20Reporter",
        "https://texas.example/es/editorial-policy",
      ]),
    );
    expect(entries.some((entry) => entry.url.includes("/admin"))).toBe(false);
    expect(entries.some((entry) => entry.url.includes("/for-you"))).toBe(false);
  });

  it("emits valid escaped Google News XML for the two-day window", async () => {
    const response = await newsSitemap.GET();
    const body = await response.text();
    expect(response.headers.get("content-type")).toContain("application/xml");
    expect(body).toContain("Austin &amp; music");
    expect(body).toContain("<news:language>es</news:language>");
    expect(body).not.toContain("Local <reporting>");
  });

  it("stops pagination if the feed repeats a cursor", async () => {
    getPublicIndexPage.mockResolvedValue({
      portal,
      feed: "latest",
      scope: null,
      label: "Latest",
      language: "en",
      canonical_url: "https://texas.example/latest",
      alternates: {},
      items: [story],
      next_cursor: "same",
    });
    await expect(getAllPublicStories("en")).rejects.toThrow(
      "Public feed returned a repeated cursor",
    );
  });
});
