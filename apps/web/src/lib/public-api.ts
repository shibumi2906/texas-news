import { cache } from "react";

export type Category = { name: string; slug: string };
export type Geography = { name: string; slug: string; type: string };
export type Entity = { id: string; name: string; slug: string; type: string };
export type Source = { name: string; url: string | null };
export type Media = {
  type: string;
  url: string;
  thumbnail_url: string | null;
  width: number | null;
  height: number | null;
  attribution: string | null;
};

export type Portal = {
  name: string;
  slug: string;
  domain: string;
  timezone: string;
  default_language: string;
  supported_languages: string[];
  canonical_url: string;
  branding: Record<string, unknown>;
  categories: Category[];
};

export type StorySummary = {
  id: string;
  slug: string;
  url: string;
  canonical_url: string;
  language: string;
  alternates: Record<string, string>;
  content_type: string;
  title: string;
  subtitle: string | null;
  description: string | null;
  author: string | null;
  published_at: string;
  updated_at: string;
  source: Source | null;
  categories: Category[];
  geography: Geography[];
  media: Media[];
};

export type Homepage = {
  portal: Portal;
  language: string;
  canonical_url: string;
  alternates: Record<string, string>;
  hero: StorySummary | null;
  trending: StorySummary[];
  category_sections: { category: Category; items: StorySummary[] }[];
  video_highlights: StorySummary[];
};

export type FeedPageData = {
  portal: Portal;
  feed:
    | "home"
    | "latest"
    | "category"
    | "local"
    | "trending"
    | "for_you"
    | "following";
  scope: string | null;
  label: string;
  language: string;
  canonical_url: string;
  alternates: Record<string, string>;
  items: StorySummary[];
  next_cursor: string | null;
};

export type Story = StorySummary & {
  portal: Portal;
  body: string | null;
  original_url: string | null;
  entities: Entity[];
  seo: Record<string, unknown>;
  related: StorySummary[];
};

export class PublicApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const apiBaseUrl = (
  process.env.API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new PublicApiError(
      response.status,
      `Public API request failed: ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export const getHomepage = cache((language = "en") =>
  request<Homepage>(
    `/api/v1/portals/texas/home?${new URLSearchParams({ language })}`,
  ),
);

type FeedKind = "home" | "latest" | "trending" | "category" | "local";

function feedPath(kind: FeedKind, scope?: string): string {
  if (kind === "category")
    return `categories/${encodeURIComponent(scope ?? "")}`;
  if (kind === "local") return `local/${encodeURIComponent(scope ?? "")}`;
  return kind;
}

export const getFeed = cache(
  (
    kind: FeedKind,
    scope?: string,
    cursor?: string,
    limit = 12,
    language = "en",
  ) => {
    const query = new URLSearchParams({ language, limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<FeedPageData>(
      `/api/v1/portals/texas/feeds/${feedPath(kind, scope)}?${query}`,
    );
  },
);

export const getCategory = (slug: string, cursor?: string, language = "en") =>
  getFeed("category", slug, cursor, 12, language);

export const getLatest = (cursor?: string, language = "en") =>
  getFeed("latest", undefined, cursor, 12, language);

export const getTrending = (cursor?: string, language = "en") =>
  getFeed("trending", undefined, cursor, 12, language);

export const getLocal = (geography: string, cursor?: string, language = "en") =>
  getFeed("local", geography, cursor, 12, language);

export const getStory = cache((slug: string, language = "en") =>
  request<Story>(
    `/api/v1/portals/texas/stories/${encodeURIComponent(slug)}?${new URLSearchParams({ language })}`,
  ),
);

export type SearchPageData = {
  portal: Portal;
  language: string;
  query: string;
  items: StorySummary[];
  next_cursor: string | null;
};

export const getSearch = (params: URLSearchParams) =>
  request<SearchPageData>(`/api/v1/portals/texas/search?${params}`);
