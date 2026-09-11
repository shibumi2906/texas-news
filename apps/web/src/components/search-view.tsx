import Link from "next/link";
import { SiteHeader, StoryCard } from "@/components/public-site";
import type { SearchPageData } from "@/lib/public-api";
import { AiAssistant } from "@/components/ai-assistant";

export function SearchView({
  data,
  params,
  error,
  language = data?.language ?? "en",
}: {
  data?: SearchPageData;
  params: Record<string, string>;
  error?: string;
  language?: string;
}) {
  const restart = new URLSearchParams(params);
  restart.delete("cursor");
  const next = new URLSearchParams(restart);
  if (data?.next_cursor) next.set("cursor", data.next_cursor);
  const portal = data?.portal;
  const base =
    portal && language !== portal.default_language ? `/${language}` : "";
  const alternateQuery = restart.toString();
  const alternates = portal
    ? Object.fromEntries(
        portal.supported_languages.map((item) => [
          item,
          `${portal.canonical_url}${item === portal.default_language ? "" : `/${item}`}/search${alternateQuery ? `?${alternateQuery}` : ""}`,
        ]),
      )
    : undefined;
  return (
    <>
      {data && (
        <SiteHeader
          portal={data.portal}
          language={language}
          alternates={alternates}
        />
      )}
      <main className="page-width listing-page">
        <h1>Search Texas stories</h1>
        <p>
          Find published stories by keyword, entity, location, category or
          publication date.
        </p>
        <AiAssistant language={language} />
        <form
          action={`${base}/search`}
          method="get"
          className="search-form"
          role="search"
        >
          <label>
            Keywords
            <input
              name="q"
              maxLength={200}
              defaultValue={params.q}
              type="search"
            />
          </label>
          <label>
            Entity name or slug
            <input
              name="entity"
              maxLength={180}
              defaultValue={params.entity}
              placeholder="Dallas Mavericks"
            />
          </label>
          <label>
            Location slug
            <input
              name="geography"
              maxLength={180}
              defaultValue={params.geography}
              placeholder="austin"
            />
          </label>
          <label>
            Category
            <select name="category" defaultValue={params.category || ""}>
              <option value="">All categories</option>
              {data?.portal.categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
              {!data && params.category && (
                <option value={params.category}>{params.category}</option>
              )}
            </select>
          </label>
          <label>
            Published from (UTC)
            <input
              name="date_from"
              type="date"
              defaultValue={params.date_from}
            />
          </label>
          <label>
            Published through (UTC)
            <input name="date_to" type="date" defaultValue={params.date_to} />
          </label>
          <button type="submit">Search</button>
          <Link href={`${base}/search`}>Clear filters</Link>
        </form>
        {error ? (
          <div role="alert">
            <p>{error}</p>
            <Link href={`${base}/search?${restart}`}>Restart search</Link>
          </div>
        ) : (
          <>
            <h2>
              {data?.query
                ? `Results for “${data.query}”`
                : "Published stories"}
            </h2>
            {data?.items.length ? (
              <div className="listing-grid">
                {data.items.map((story) => (
                  <StoryCard key={story.id} story={story} />
                ))}
              </div>
            ) : (
              <p>No stories found. Try other words or fewer filters.</p>
            )}
            {data?.next_cursor && (
              <Link className="pagination" href={`${base}/search?${next}`}>
                Next results
              </Link>
            )}
          </>
        )}
      </main>
    </>
  );
}
