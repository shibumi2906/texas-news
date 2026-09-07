import type { Metadata } from "next";
import { SearchView } from "@/components/search-view";
import { getSearch, PublicApiError } from "@/lib/public-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Search",
  robots: { index: false, follow: true },
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const params: Record<string, string> = {};
  for (const key of [
    "q",
    "entity",
    "geography",
    "category",
    "date_from",
    "date_to",
    "cursor",
    "language",
  ]) {
    if (typeof raw[key] === "string" && raw[key]) params[key] = raw[key];
  }
  const query = new URLSearchParams({
    ...params,
    language: params.language || "en",
    limit: "12",
  });
  let data;
  let message: string | undefined;
  try {
    data = await getSearch(query);
  } catch (error) {
    if (!(error instanceof PublicApiError)) throw error;
    message =
      error.status === 400
        ? "The results have changed or this page link has expired. Restart your search."
        : error.status === 404
          ? "This location, category or language is not available for this portal."
          : error.status === 422
            ? "Check your search text and dates. The start date must come before the end date."
            : "Search is temporarily unavailable. Please try again.";
  }
  return <SearchView data={data} params={params} error={message} />;
}
