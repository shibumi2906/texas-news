import type { Portal, Story } from "@/lib/public-api";

function safeHttpUrl(value: string | null | undefined) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

function JsonLd({ value }: { value: object }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(value).replace(/</g, "\\u003c"),
      }}
    />
  );
}

export function PublisherStructuredData({ portal }: { portal: Portal }) {
  const logo = safeHttpUrl(portal.logo);
  return (
    <JsonLd
      value={{
        "@context": "https://schema.org",
        "@graph": [
          {
            "@type": "NewsMediaOrganization",
            "@id": `${portal.canonical_url}/#publisher`,
            name: portal.name,
            url: portal.canonical_url,
            ...(logo ? { logo: { "@type": "ImageObject", url: logo } } : {}),
          },
          {
            "@type": "WebSite",
            "@id": `${portal.canonical_url}/#website`,
            name: portal.name,
            url: portal.canonical_url,
            publisher: { "@id": `${portal.canonical_url}/#publisher` },
            inLanguage: portal.supported_languages,
          },
        ],
      }}
    />
  );
}

export function StoryStructuredData({ story }: { story: Story }) {
  const portal = story.portal;
  const authorUrl = story.author
    ? `${portal.canonical_url}${story.language === portal.default_language ? "" : `/${story.language}`}/authors/${encodeURIComponent(story.author)}`
    : undefined;
  const images = story.media
    .map((media) => ({
      url: safeHttpUrl(media.url),
      width: media.width ?? undefined,
      height: media.height ?? undefined,
    }))
    .filter((image) => image.url);
  const logo = safeHttpUrl(portal.logo);
  const originalUrl = safeHttpUrl(story.original_url);
  const publisher = {
    "@type": "NewsMediaOrganization",
    "@id": `${portal.canonical_url}/#publisher`,
    name: portal.name,
    url: portal.canonical_url,
    ...(logo ? { logo: { "@type": "ImageObject", url: logo } } : {}),
  };
  const prefix =
    story.language === portal.default_language ? "" : `/${story.language}`;
  const primaryCategory = story.categories[0];
  const breadcrumbs = [
    {
      "@type": "ListItem",
      position: 1,
      name: portal.name,
      item: `${portal.canonical_url}${prefix}`,
    },
    ...(primaryCategory
      ? [
          {
            "@type": "ListItem",
            position: 2,
            name: primaryCategory.name,
            item: `${portal.canonical_url}${prefix}/${primaryCategory.slug}`,
          },
        ]
      : []),
    {
      "@type": "ListItem",
      position: primaryCategory ? 3 : 2,
      name: story.title,
      item: story.canonical_url,
    },
  ];
  return (
    <JsonLd
      value={{
        "@context": "https://schema.org",
        "@graph": [
          {
            "@type": "NewsArticle",
            "@id": `${story.canonical_url}#article`,
            headline: story.title,
            description: story.description ?? story.subtitle ?? story.title,
            datePublished: story.published_at,
            dateModified: story.updated_at,
            mainEntityOfPage: {
              "@type": "WebPage",
              "@id": story.canonical_url,
            },
            inLanguage: story.language,
            articleSection: story.categories.map((category) => category.name),
            contentLocation: story.geography.map((place) => ({
              "@type": "Place",
              name: place.name,
            })),
            keywords: [
              ...story.categories.map((category) => category.name),
              ...story.entities.map((entity) => entity.name),
              ...story.geography.map((place) => place.name),
            ],
            image: images,
            author: story.author
              ? { "@type": "Person", name: story.author, url: authorUrl }
              : publisher,
            publisher,
            ...(originalUrl ? { isBasedOn: originalUrl } : {}),
          },
          {
            "@type": "BreadcrumbList",
            itemListElement: breadcrumbs,
          },
        ],
      }}
    />
  );
}
