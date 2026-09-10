import Link from "next/link";

import { AiStorySummary } from "@/components/ai-story-summary";
import { CommunityPanel } from "@/components/community";

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
        {new Intl.DateTimeFormat("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
          timeZone: "America/Chicago",
        }).format(new Date(story.published_at))}
      </time>
    </p>
  );
}

export function SiteHeader({ portal }: { portal: Portal }) {
  return (
    <header className="site-header">
      <div className="header-top page-width">
        <Link
          className="brand"
          href="/"
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
      <nav className="category-nav" aria-label="Primary navigation">
        <div className="page-width nav-scroll">
          <Link href="/">Home</Link>
          <Link href="/latest">Latest</Link>
          <Link href="/search">Search</Link>
          <Link href="/trending">Trending</Link>
          <Link href="/for-you">For You</Link>
          <Link href="/following">Following</Link>
          <Link href="/local/texas">Local</Link>
          {portal.categories.map((category) => (
            <Link href={`/${category.slug}`} key={category.slug}>
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

function SectionHeading({ title, href }: { title: string; href?: string }) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {href ? <Link href={href}>View all</Link> : null}
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
      <SiteHeader portal={data.portal} />
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
                <SectionHeading title="Trending in Texas" />
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
                  href={`/${section.category.slug}`}
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
      <SiteHeader portal={data.portal} />
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

function ShareControls({ story }: { story: Story }) {
  const encodedUrl = encodeURIComponent(story.canonical_url);
  const encodedTitle = encodeURIComponent(story.title);
  return (
    <nav className="share-controls" aria-label="Share this story">
      <span>Share</span>
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
  return (
    <>
      <SiteHeader portal={portal} />
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
          <div className="story-primary-media">
            <MediaFrame story={story} priority />
            {primaryMedia(story)?.attribution ? (
              <small>{primaryMedia(story)?.attribution}</small>
            ) : null}
          </div>
          <ShareControls story={story} />
          <AiStorySummary
            storySlug={story.slug}
            language={story.portal.default_language}
          />
          <div className="story-body">
            {paragraphs.length ? (
              paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)
            ) : (
              <p>{story.description}</p>
            )}
          </div>
          <footer className="story-taxonomy">
            {story.categories.map((category) => (
              <Link href={`/${category.slug}`} key={category.slug}>
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
          <CommunityPanel storySlug={story.slug} entities={story.entities} />
        </article>
        {story.related.length ? (
          <aside className="related-stories">
            <SectionHeading title="Related stories" />
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
