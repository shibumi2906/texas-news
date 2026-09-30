import {
  getHomepage,
  getPublicIndexPage,
  type Portal,
  type StorySummary,
} from "@/lib/public-api";

export const TRUST_PATHS = [
  "about",
  "contact",
  "editorial-policy",
  "corrections",
  "ownership",
] as const;

export type TrustPath = (typeof TRUST_PATHS)[number];

export function localizedPath(portal: Portal, language: string, path = "") {
  const prefix = language === portal.default_language ? "" : `/${language}`;
  return `${portal.canonical_url}${prefix}${path}`;
}

export async function getAllPublicStories(
  language: string,
  maximum = 50_000,
): Promise<StorySummary[]> {
  const stories: StorySummary[] = [];
  const cursors = new Set<string>();
  const identities = new Set<string>();
  let cursor: string | undefined;
  do {
    const page = await getPublicIndexPage(cursor, language);
    for (const story of page.items) {
      if (!identities.has(story.id) && stories.length < maximum) {
        identities.add(story.id);
        stories.push(story);
      }
    }
    if (stories.length >= maximum || !page.next_cursor) break;
    if (cursors.has(page.next_cursor)) {
      throw new Error("Public feed returned a repeated cursor");
    }
    cursors.add(page.next_cursor);
    cursor = page.next_cursor;
  } while (cursor);
  return stories;
}

export async function getDiscoveryContent(maximumStories = 44_000) {
  const home = await getHomepage();
  const byLanguage = new Map<string, StorySummary[]>();
  const perLanguage = Math.max(
    1,
    Math.floor(maximumStories / home.portal.supported_languages.length),
  );
  await Promise.all(
    home.portal.supported_languages.map(async (language) => {
      byLanguage.set(
        language,
        await getAllPublicStories(language, perLanguage),
      );
    }),
  );
  return { portal: home.portal, byLanguage };
}

export function xml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}
