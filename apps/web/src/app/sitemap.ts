import type { MetadataRoute } from "next";

import {
  getDiscoveryContent,
  localizedPath,
  TRUST_PATHS,
} from "@/lib/discovery";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const { portal, byLanguage } = await getDiscoveryContent();
  const entries: MetadataRoute.Sitemap = [];
  const seen = new Set<string>();
  let authorCount = 0;
  const add = (entry: MetadataRoute.Sitemap[number]) => {
    if (seen.has(entry.url)) return false;
    seen.add(entry.url);
    entries.push(entry);
    return true;
  };
  const alternates = (path: string) => ({
    languages: Object.fromEntries(
      portal.supported_languages.map((language) => [
        language,
        localizedPath(portal, language, path),
      ]),
    ),
  });

  for (const language of portal.supported_languages) {
    const prefix = language === portal.default_language ? "" : `/${language}`;
    const languageAlternates = Object.fromEntries(
      portal.supported_languages.map((item) => [
        item,
        localizedPath(portal, item),
      ]),
    );
    add({
      url: localizedPath(portal, language),
      changeFrequency: "hourly",
      priority: 1,
      alternates: { languages: languageAlternates },
    });
    for (const path of ["latest", "trending", "shorts"]) {
      add({
        url: `${portal.canonical_url}${prefix}/${path}`,
        changeFrequency: "hourly",
        priority: 0.8,
        alternates: alternates(`/${path}`),
      });
    }
    for (const category of portal.categories) {
      add({
        url: `${portal.canonical_url}${prefix}/${category.slug}`,
        changeFrequency: "hourly",
        priority: 0.8,
        alternates: alternates(`/${category.slug}`),
      });
    }
    for (const path of TRUST_PATHS) {
      add({
        url: `${portal.canonical_url}${prefix}/${path}`,
        changeFrequency: "monthly",
        priority: 0.5,
        alternates: alternates(`/${path}`),
      });
    }
    for (const story of byLanguage.get(language) ?? []) {
      add({
        url: story.canonical_url,
        lastModified: story.updated_at,
        changeFrequency: "weekly",
        priority: 0.7,
        alternates: { languages: story.alternates },
        images: story.media
          .map((media) => media.url)
          .filter(
            (url) => url.startsWith("https://") || url.startsWith("http://"),
          ),
      });
      if (story.author && authorCount < 1_000) {
        if (
          add({
            url: `${portal.canonical_url}${prefix}/authors/${encodeURIComponent(story.author)}`,
            changeFrequency: "weekly",
            priority: 0.5,
            alternates: {
              languages: Object.fromEntries(
                Object.keys(story.alternates).map((candidate) => [
                  candidate,
                  localizedPath(
                    portal,
                    candidate,
                    `/authors/${encodeURIComponent(story.author!)}`,
                  ),
                ]),
              ),
            },
          })
        ) {
          authorCount += 1;
        }
      }
    }
  }
  return entries;
}
