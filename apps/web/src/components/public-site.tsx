import Link from "next/link";

import { AiStorySummary } from "@/components/ai-story-summary";
import { AiAssistant } from "@/components/ai-assistant";
import { CommunityPanel } from "@/components/community";
import { GalleryExperience, ShortsFeed } from "@/components/media-experience";

import type {
  FeedPageData,
  Homepage,
  Media,
  Portal,
  Story,
  StorySummary,
} from "@/lib/public-api";

function primaryMedia(story: StorySummary): Media | undefined {
  return story.media[0];
}

function prefix(language: string, portal: Portal) {
  return language === portal.default_language ? "" : `/${language}`;
}

function localPath(url: string) {
  try {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return url;
  }
}

const copy = {
  en: {
    home: "Home",
    latest: "Latest",
    search: "Search",
    trending: "Trending",
    forYou: "For You",
    following: "Following",
    local: "Local",
    viewAll: "View all",
    share: "Share",
    related: "Related stories",
    shorts: "Shorts",
    media: "More ways to experience Texas",
  },
  es: {
    home: "Inicio",
    latest: "Últimas",
    search: "Buscar",
    trending: "Tendencias",
    forYou: "Para ti",
    following: "Siguiendo",
    local: "Local",
    viewAll: "Ver todo",
    share: "Compartir",
    related: "Historias relacionadas",
    shorts: "Videos cortos",
    media: "Más formas de vivir Texas",
  },
} as const;

function ui(language: string) {
  return language === "es" ? copy.es : copy.en;
}

function MediaFrame({ story }: { story: StorySummary; priority?: boolean }) {
  const media = primaryMedia(story);
  const source = media?.thumbnail_url ?? media?.url;
  if (!source) {
    return (
      <div className="media-frame media-fallback" aria-hidden="true">
        <span>★</span>
      </div>
    );
  }
  return (
    <div
      className="media-frame media-image"
      style={{ backgroundImage: `url(${JSON.stringify(source)})` }}
      aria-hidden="true"
    />
  );
}

function CategoryBadge({ story }: { story: StorySummary }) {
  const category = story.categories[0];
  return category ? <span className="badge">{category.name}</span> : null;
}

function StoryMeta({ story }: { story: StorySummary }) {
  return (
    <p className="story-meta">
      {story.geography[0]?.name ?? "Texas"} ·{" "}
      <time dateTime={story.published_at}>
        {new Intl.DateTimeFormat(story.language === "es" ? "es-US" : "en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
          timeZone: "America/Chicago",
        }).format(new Date(story.published_at))}
      </time>
    </p>
  );
}

export function SiteHeader({
  portal,
  language = portal.default_language,
  alternates,
}: {
  portal: Portal;
  language?: string;
  alternates?: Record<string, string>;
}) {
  const base = prefix(language, portal);
  const labels = ui(language);
  return (
    <header className="site-header">
      <div className="header-top page-width">
        <Link
          className="brand"
          href={base || "/"}
          aria-label="Texas Entertainment Daily home"
        >
          <span className="brand-star">★</span>
          <span>
            <strong>TEXAS</strong>
            <small>ENTERTAINMENT DAILY</small>
          </span>
        </Link>
        <p className="portal-tagline">
          {typeof portal.branding.tagline === "string"
            ? portal.branding.tagline
            : "Stories, culture and entertainment across the Lone Star State"}
        </p>
      </div>
      <nav className="language-switch" aria-label="Language">
        {portal.supported_languages.map((item) => {
          const target = alternates?.[item];
          return target ? (
            <Link
              key={item}
              href={localPath(target)}
              hrefLang={item}
              aria-current={item === language ? "page" : undefined}
            >
              {item === "es" ? "Español" : "English"}
            </Link>
          ) : null;
        })}
      </nav>
      <nav className="category-nav" aria-label="Primary navigation">
        <div className="page-width nav-scroll">
          <Link href={base || "/"}>{labels.home}</Link>
          <Link href={`${base}/latest`}>{labels.latest}</Link>
          <Link href={`${base}/search`}>{labels.search}</Link>
          <Link href={`${base}/trending`}>{labels.trending}</Link>
          <Link href={`${base}/shorts`}>{labels.shorts}</Link>
          <Link href={`${base}/for-you`}>{labels.forYou}</Link>
          <Link href={`${base}/following`}>{labels.following}</Link>
          <Link href={`${base}/local/texas`}>{labels.local}</Link>
          {portal.categories.map((category) => (
            <Link href={`${base}/${category.slug}`} key={category.slug}>
              {category.name}
            </Link>
          ))}
        </div>
      </nav>
    </header>
  );
}

export function StoryCard({
  story,
  compact = false,
}: {
  story: StorySummary;
  compact?: boolean;
}) {
  return (
    <article className={`story-card${compact ? " compact" : ""}`}>
      <Link href={story.url} aria-label={story.title}>
        <MediaFrame story={story} />
      </Link>
      <div className="card-copy">
        <span className="content-type-label">{story.content_type}</span>
        <CategoryBadge story={story} />
        <h3>
          <Link href={story.url}>{story.title}</Link>
        </h3>
        {!compact && story.description ? <p>{story.description}</p> : null}
        <StoryMeta story={story} />
      </div>
    </article>
  );
}

function SectionHeading({
  title,
  href,
  language = "en",
}: {
  title: string;
  href?: string;
  language?: string;
}) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {href ? <Link href={href}>{ui(language).viewAll}</Link> : null}
    </div>
  );
}

function EmptyNewsroom() {
  return (
    <section className="empty-newsroom">
      <span aria-hidden="true">★</span>
      <h1>Texas stories are on the way</h1>
      <p>
        Published reporting will appear here as soon as it clears the newsroom.
      </p>
    </section>
  );
}

export function HomeView({ data }: { data: Homepage }) {
  const populatedSections = data.category_sections.filter(
    (section) => section.items.length > 0,
  );
  return (
    <>
      <SiteHeader
        portal={data.portal}
        language={data.language}
        alternates={data.alternates}
      />
      <main className="page-width home-layout">
        {!data.hero ? (
          <EmptyNewsroom />
        ) : (
          <>
            <section className="lead-grid" aria-label="Top Texas stories">
              <article className="hero-story">
                <MediaFrame story={data.hero} priority />
                <div className="hero-shade" />
                <div className="hero-copy">
                  <CategoryBadge story={data.hero} />
                  <h1>
                    <Link href={data.hero.url}>{data.hero.title}</Link>
                  </h1>
                  {data.hero.description ? (
                    <p>{data.hero.description}</p>
                  ) : null}
                  <StoryMeta story={data.hero} />
                </div>
              </article>
              <aside className="trending-panel">
                <SectionHeading
                  title={
                    data.language === "es"
                      ? "Tendencias en Texas"
                      : "Trending in Texas"
                  }
                  language={data.language}
                />
                {data.trending.length ? (
                  <ol>
                    {data.trending.map((story) => (
                      <li key={story.id}>
                        <span className="trend-number" aria-hidden="true" />
                        <div>
                          <CategoryBadge story={story} />
                          <Link href={story.url}>{story.title}</Link>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="quiet-copy">
                    More published stories will appear here.
                  </p>
                )}
              </aside>
            </section>

            {populatedSections.map((section) => (
              <section
                className="editorial-section"
                key={section.category.slug}
              >
                <SectionHeading
                  title={section.category.name}
                  href={`${prefix(data.language, data.portal)}/${section.category.slug}`}
                  language={data.language}
                />
                <div className="card-grid">
                  {section.items.map((story) => (
                    <StoryCard story={story} key={story.id} />
                  ))}
                </div>
              </section>
            ))}

            <section className="editorial-section video-section">
              <SectionHeading title="Video highlights" />
              {data.video_highlights.length ? (
                <div className="card-grid video-grid">
                  {data.video_highlights.map((story) => (
                    <StoryCard story={story} compact key={story.id} />
                  ))}
                </div>
              ) : (
                <p className="quiet-copy">
                  Video reporting will appear here when published.
                </p>
              )}
            </section>

            <section className="editorial-section media-section">
              <SectionHeading
                title={ui(data.language).media}
                language={data.language}
              />
              {data.media_highlights.length ? (
                <div className="card-grid">
                  {data.media_highlights.map((story) => (
                    <StoryCard story={story} key={story.id} />
                  ))}
                </div>
              ) : (
                <p className="quiet-copy">
                  Galleries, memes, Shorts, events and live coverage will appear
                  here when published.
                </p>
              )}
            </section>
          </>
        )}
      </main>
      <SiteFooter portal={data.portal} />
    </>
  );
}

export function FeedView({
  data,
  title = data.label,
  deck = `The latest published ${data.label.toLowerCase()} stories.`,
  path,
}: {
  data: FeedPageData;
  title?: string;
  deck?: string;
  path: string;
}) {
  return (
    <>
      <SiteHeader
        portal={data.portal}
        language={data.language}
        alternates={data.alternates}
      />
      <main className="page-width listing-page">
        <div className="page-kicker">Explore Texas</div>
        <h1>{title}</h1>
        <p className="page-deck">{deck}</p>
        {data.items.length ? (
          <div className="listing-grid">
            {data.items.map((story) => (
              <StoryCard story={story} key={story.id} />
            ))}
          </div>
        ) : (
          <p className="quiet-copy">
            No published stories in this section yet.
          </p>
        )}
        <nav className="pagination" aria-label={`${title} feed pages`}>
          <span />
          {data.next_cursor ? (
            <Link
              href={`${path}?cursor=${encodeURIComponent(data.next_cursor)}`}
            >
              Older →
            </Link>
          ) : null}
        </nav>
      </main>
      <SiteFooter portal={data.portal} />
    </>
  );
}

export function CategoryView({ data }: { data: FeedPageData }) {
  return <FeedView data={data} path={`/${data.scope ?? ""}`} />;
}

export function ShortsView({ data }: { data: FeedPageData }) {
  const languagePrefix =
    data.language === data.portal.default_language ? "" : `/${data.language}`;
  const nextHref = data.next_cursor
    ? `${languagePrefix}/shorts?${new URLSearchParams({ cursor: data.next_cursor })}`
    : undefined;
  return (
    <>
      <SiteHeader
        portal={data.portal}
        language={data.language}
        alternates={data.alternates}
      />
      <main className="shorts-page">
        <h1 className="visually-hidden">{data.label}</h1>
        <ShortsFeed
          items={data.items}
          portalSlug={data.portal.slug}
          nextHref={nextHref}
        />
      </main>
      <SiteFooter portal={data.portal} />
    </>
  );
}

function ShareControls({ story }: { story: Story }) {
  const encodedUrl = encodeURIComponent(story.canonical_url);
  const encodedTitle = encodeURIComponent(story.title);
  return (
    <nav className="share-controls" aria-label="Share this story">
      <span>{ui(story.language).share}</span>
      <a href={`https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`}>
        Facebook
      </a>
      <a
        href={`https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedTitle}`}
      >
        X
      </a>
      <a href={`mailto:?subject=${encodedTitle}&body=${encodedUrl}`}>Email</a>
    </nav>
  );
}

export function StoryView({ story, portal }: { story: Story; portal: Portal }) {
  const paragraphs = story.body?.split(/\n\s*\n/).filter(Boolean) ?? [];
  if (story.content_type === "short") {
    const relatedShorts = story.related.filter(
      (item) => item.content_type === "short",
    );
    return (
      <>
        <SiteHeader
          portal={portal}
          language={story.language}
          alternates={story.alternates}
        />
        <main className="shorts-page">
          <h1 className="visually-hidden">{story.title}</h1>
          <ShortsFeed
            items={[story, ...relatedShorts]}
            portalSlug={portal.slug}
          />
        </main>
        <SiteFooter portal={portal} />
      </>
    );
  }
  const primaryVideo = story.media.find((item) => item.type === "video");
  const primaryImage = story.media.find((item) => item.type === "image");
  const venue = story.entities.find((item) => item.type === "venue");
  return (
    <>
      <SiteHeader
        portal={portal}
        language={story.language}
        alternates={story.alternates}
      />
      <main className="page-width story-page">
        <article>
          <header className="story-header">
            <CategoryBadge story={story} />
            <h1>{story.title}</h1>
            {story.subtitle ? (
              <p className="story-subtitle">{story.subtitle}</p>
            ) : null}
            <div className="byline">
              <span>
                {story.author
                  ? `By ${story.author}`
                  : "Texas Entertainment Daily"}
              </span>
              {story.source ? <span>Source: {story.source.name}</span> : null}
              <time dateTime={story.published_at}>
                Published{" "}
                {new Date(story.published_at).toLocaleString("en-US", {
                  timeZone: portal.timezone,
                })}
              </time>
              {story.updated_at !== story.published_at ? (
                <time dateTime={story.updated_at}>
                  Updated{" "}
                  {new Date(story.updated_at).toLocaleString("en-US", {
                    timeZone: portal.timezone,
                  })}
                </time>
              ) : null}
            </div>
          </header>
          {story.content_type === "gallery" ? (
            <GalleryExperience key={story.id} story={story} />
          ) : story.content_type === "live" && primaryVideo ? (
            <section
              className="live-experience"
              aria-label={
                story.language === "es" ? "Cobertura en vivo" : "Live coverage"
              }
            >
              <span className="live-indicator">
                {story.language === "es"
                  ? "Cobertura en vivo"
                  : "Live coverage"}
              </span>
              <video
                src={primaryVideo.url}
                poster={primaryVideo.thumbnail_url ?? undefined}
                controls
                autoPlay
                muted
                playsInline
              >
                Your browser does not support video playback.
              </video>
            </section>
          ) : story.content_type === "meme" && primaryImage ? (
            <figure className="meme-experience">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={primaryImage.url} alt={story.title} />
              {primaryImage.attribution ? (
                <figcaption>{primaryImage.attribution}</figcaption>
              ) : null}
            </figure>
          ) : (
            <div className="story-primary-media">
              <MediaFrame story={story} priority />
              {primaryMedia(story)?.attribution ? (
                <small>{primaryMedia(story)?.attribution}</small>
              ) : null}
            </div>
          )}
          {story.content_type === "event" ? (
            <aside
              className="event-facts"
              aria-label={
                story.language === "es"
                  ? "Detalles del evento"
                  : "Event details"
              }
            >
              <strong>
                {story.language === "es"
                  ? "Detalles del evento"
                  : "Event details"}
              </strong>
              {venue ? (
                <span>
                  {story.language === "es" ? "Lugar" : "Venue"}: {venue.name}
                </span>
              ) : null}
              {story.geography.map((place) => (
                <span key={place.slug}>
                  {story.language === "es" ? "Ubicación" : "Location"}:{" "}
                  {place.name}
                </span>
              ))}
              {!venue && !story.geography.length ? (
                <span>
                  {story.language === "es"
                    ? "La redacción añadirá los detalles."
                    : "Details will be added by the newsroom."}
                </span>
              ) : null}
            </aside>
          ) : null}
          <ShareControls story={story} />
          {story.content_type === "article" ? (
            <>
              <AiStorySummary
                storySlug={story.slug}
                language={story.language}
              />
              <AiAssistant storySlug={story.slug} language={story.language} />
            </>
          ) : null}
          <div className="story-body">
            {paragraphs.length ? (
              paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)
            ) : (
              <p>{story.description}</p>
            )}
          </div>
          <footer className="story-taxonomy">
            {story.categories.map((category) => (
              <Link
                href={`${prefix(story.language, portal)}/${category.slug}`}
                key={category.slug}
              >
                {category.name}
              </Link>
            ))}
            {story.geography.map((place) => (
              <span key={place.slug}>{place.name}</span>
            ))}
            {story.entities.map((entity) => (
              <span key={entity.slug}>{entity.name}</span>
            ))}
          </footer>
          <CommunityPanel
            portalSlug={portal.slug}
            language={story.language}
            storySlug={story.slug}
            entities={story.entities}
          />
        </article>
        {story.related.length ? (
          <aside className="related-stories">
            <SectionHeading
              title={ui(story.language).related}
              language={story.language}
            />
            <div className="related-grid">
              {story.related.map((item) => (
                <StoryCard story={item} compact key={item.id} />
              ))}
            </div>
          </aside>
        ) : null}
      </main>
      <SiteFooter portal={portal} />
    </>
  );
}

function SiteFooter({ portal }: { portal: Portal }) {
  return (
    <footer className="site-footer">
      <div className="page-width">
        <strong>{portal.name}</strong>
        <span>Local stories. Texas perspective.</span>
      </div>
    </footer>
  );
}
