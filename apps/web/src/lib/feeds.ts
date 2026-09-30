import { getAllPublicStories, xml } from "@/lib/discovery";
import { getHomepage } from "@/lib/public-api";

export async function rssResponse(language: string) {
  const home = await getHomepage(language);
  const stories = (await getAllPublicStories(language, 50)).slice(0, 50);
  const items = stories
    .map(
      (story) => `  <item>
    <guid isPermaLink="true">${xml(story.canonical_url)}</guid>
    <link>${xml(story.canonical_url)}</link>
    <title>${xml(story.title)}</title>
    <description>${xml(story.description ?? story.subtitle ?? story.title)}</description>
    <pubDate>${new Date(story.published_at).toUTCString()}</pubDate>
  </item>`,
    )
    .join("\n");
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>${xml(home.portal.name)}</title>
  <link>${xml(home.canonical_url)}</link>
  <description>${xml(typeof home.portal.branding.tagline === "string" ? home.portal.branding.tagline : "Local entertainment news")}</description>
  <language>${xml(language)}</language>
  <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${items}
</channel>
</rss>`,
    {
      headers: {
        "Content-Type": "application/rss+xml; charset=utf-8",
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      },
    },
  );
}
