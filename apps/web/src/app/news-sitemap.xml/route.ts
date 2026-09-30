import { getDiscoveryContent, xml } from "@/lib/discovery";

export const dynamic = "force-dynamic";

export async function GET() {
  const { portal, byLanguage } = await getDiscoveryContent(2_000);
  const cutoff = Date.now() - 2 * 24 * 60 * 60 * 1000;
  const stories = [...byLanguage.values()]
    .flat()
    .filter((story) => new Date(story.published_at).getTime() >= cutoff)
    .sort(
      (left, right) =>
        new Date(right.published_at).getTime() -
        new Date(left.published_at).getTime(),
    )
    .slice(0, 1_000);
  const urls = stories
    .map(
      (story) => `  <url>
    <loc>${xml(story.canonical_url)}</loc>
    <news:news>
      <news:publication>
        <news:name>${xml(portal.name)}</news:name>
        <news:language>${xml(story.language)}</news:language>
      </news:publication>
      <news:publication_date>${xml(story.published_at)}</news:publication_date>
      <news:title>${xml(story.title)}</news:title>
    </news:news>
  </url>`,
    )
    .join("\n");
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
${urls}
</urlset>`,
    {
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      },
    },
  );
}
