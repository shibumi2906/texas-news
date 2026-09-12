import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PersonalizedFeed } from "@/components/personalized-feed";
import {
  CategoryView,
  FeedView,
  HomeView,
  ShortsView,
  StoryView,
} from "@/components/public-site";
import { SearchView } from "@/components/search-view";
import {
  getCategory,
  getHomepage,
  getLatest,
  getLocal,
  getSearch,
  getShorts,
  getStory,
  getTrending,
  PublicApiError,
} from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ segments: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

type Route = {
  language: string;
  kind:
    | "home"
    | "category"
    | "latest"
    | "trending"
    | "local"
    | "story"
    | "search"
    | "for-you"
    | "following"
    | "shorts";
  value?: string;
};

async function resolveRoute(segments: string[]): Promise<Route> {
  if (segments.length === 1 && segments[0] === "shorts") {
    return { language: "en", kind: "shorts" };
  }
  if (segments.length === 1) {
    try {
      await getHomepage(segments[0]);
      return { language: segments[0], kind: "home" };
    } catch (error) {
      if (!(error instanceof PublicApiError) || error.status !== 404)
        throw error;
      return { language: "en", kind: "category", value: segments[0] };
    }
  }
  const [language, kind, value] = segments;
  if (
    ["latest", "trending", "search", "for-you", "following", "shorts"].includes(
      kind,
    ) &&
    segments.length === 2
  ) {
    return { language, kind: kind as Route["kind"] };
  }
  if (
    ["category", "local", "story"].includes(kind) &&
    value &&
    segments.length === 3
  ) {
    return {
      language,
      kind: kind === "category" ? "category" : (kind as Route["kind"]),
      value,
    };
  }
  if (segments.length === 2) {
    return { language, kind: "category", value: kind };
  }
  notFound();
}

function cursor(raw: Record<string, string | string[] | undefined>) {
  return typeof raw.cursor === "string" ? raw.cursor : undefined;
}

function metadataAlternates(
  canonical: string,
  languages: Record<string, string>,
) {
  return { canonical, languages };
}

async function load(props: Props) {
  const route = await resolveRoute((await props.params).segments);
  const raw = await props.searchParams;
  try {
    if (route.kind === "home")
      return { route, data: await getHomepage(route.language) };
    if (route.kind === "category") {
      return {
        route,
        data: await getCategory(route.value ?? "", cursor(raw), route.language),
      };
    }
    if (route.kind === "latest") {
      return { route, data: await getLatest(cursor(raw), route.language) };
    }
    if (route.kind === "trending") {
      return { route, data: await getTrending(cursor(raw), route.language) };
    }
    if (route.kind === "shorts") {
      return { route, data: await getShorts(cursor(raw), route.language) };
    }
    if (route.kind === "local") {
      return {
        route,
        data: await getLocal(route.value ?? "", cursor(raw), route.language),
      };
    }
    if (route.kind === "story") {
      return { route, data: await getStory(route.value ?? "", route.language) };
    }
    return { route, data: null };
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { route, data } = await load(props);
  if (route.kind === "search") {
    return {
      title: route.language === "es" ? "Buscar" : "Search",
      robots: { index: false },
    };
  }
  if (route.kind === "for-you" || route.kind === "following") return {};
  if (!data) return {};
  if (route.kind === "story" && "seo" in data) {
    const description =
      (typeof data.seo.description === "string"
        ? data.seo.description
        : null) ??
      data.description ??
      data.subtitle ??
      data.title;
    const image = data.media[0]?.thumbnail_url ?? data.media[0]?.url;
    return {
      title: typeof data.seo.title === "string" ? data.seo.title : data.title,
      description,
      alternates: metadataAlternates(data.canonical_url, data.alternates),
      openGraph: {
        title: data.title,
        description,
        type: "article",
        url: data.canonical_url,
        publishedTime: data.published_at,
        modifiedTime: data.updated_at,
        images: image ? [{ url: image }] : undefined,
      },
    };
  }
  const title =
    route.kind === "home"
      ? "Texas Entertainment Daily"
      : "label" in data
        ? data.label
        : "Texas Entertainment Daily";
  return {
    title,
    alternates: metadataAlternates(data.canonical_url, data.alternates),
  };
}

export default async function LocalizedPage(props: Props) {
  const loaded = await load(props);
  const { route, data } = loaded;
  const raw = await props.searchParams;
  const base = route.language === "en" ? "" : `/${route.language}`;
  if (route.kind === "home" && data && "hero" in data)
    return <HomeView data={data} />;
  if (route.kind === "category" && data && "feed" in data)
    return <CategoryView data={data} />;
  if (route.kind === "latest" && data && "feed" in data) {
    return <FeedView data={data} path={`${base}/latest`} />;
  }
  if (route.kind === "trending" && data && "feed" in data) {
    return <FeedView data={data} path={`${base}/trending`} />;
  }
  if (route.kind === "shorts" && data && "feed" in data) {
    return <ShortsView data={data} />;
  }
  if (route.kind === "local" && data && "feed" in data) {
    return <FeedView data={data} path={`${base}/local/${route.value}`} />;
  }
  if (route.kind === "story" && data && "seo" in data) {
    return <StoryView story={data} portal={data.portal} />;
  }
  if (route.kind === "for-you" || route.kind === "following") {
    return (
      <PersonalizedFeed
        kind={route.kind}
        language={route.language}
        cursor={cursor(raw)}
      />
    );
  }
  if (route.kind === "search") {
    const params: Record<string, string> = {};
    for (const key of [
      "q",
      "entity",
      "geography",
      "category",
      "date_from",
      "date_to",
      "cursor",
    ]) {
      if (typeof raw[key] === "string" && raw[key]) params[key] = raw[key];
    }
    const query = new URLSearchParams({
      ...params,
      language: route.language,
      limit: "12",
    });
    let searchData;
    let errorMessage: string | undefined;
    try {
      searchData = await getSearch(query);
    } catch (error) {
      if (!(error instanceof PublicApiError)) throw error;
      errorMessage =
        error.status === 400
          ? "The results changed. Restart your search."
          : "Search is temporarily unavailable.";
    }
    if (searchData) {
      return (
        <SearchView
          data={searchData}
          params={params}
          language={route.language}
        />
      );
    }
    return (
      <SearchView
        params={params}
        language={route.language}
        error={errorMessage}
      />
    );
  }
  notFound();
}
