"use client";

import Link from "next/link";
import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { CommunityPanel } from "@/components/community";
import type { Media, Story, StorySummary } from "@/lib/public-api";

function browserIdentity(name: string) {
  let value = window.localStorage.getItem(name);
  if (!value) {
    value = crypto.randomUUID();
    window.localStorage.setItem(name, value);
  }
  return value;
}

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith("news_csrf="))
    ?.split("=")
    .slice(1)
    .join("=");
}

async function event(
  portalSlug: string,
  eventType: string,
  contentId: string,
  properties: Record<string, string | number> = {},
) {
  const payload = {
    id: crypto.randomUUID(),
    event_type: eventType,
    content_id: contentId,
    timestamp: new Date().toISOString(),
    anonymous_id: browserIdentity("news_anonymous_id"),
    session_id: browserIdentity("news_session_id"),
    properties,
  };
  await fetch(
    `/api/v1/portals/${encodeURIComponent(portalSlug)}/analytics/events`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
      keepalive: true,
    },
  );
}

async function communityAction(
  portalSlug: string,
  path: string,
  method: "PUT" | "DELETE",
  body?: object,
) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const csrf = csrfToken();
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch(
    `/api/v1/portals/${encodeURIComponent(portalSlug)}/community${path}`,
    {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    },
  );
  if (!response.ok) throw new Error(String(response.status));
}

function imageSource(media: Media | undefined) {
  return media?.thumbnail_url ?? media?.url;
}

export function GalleryExperience({ story }: { story: Story }) {
  const images = story.media.filter((item) => item.type === "image");
  const spanish = story.language === "es";
  const [index, setIndex] = useState(0);
  const current = images[index];
  const select = useCallback(
    (next: number) => setIndex((next + images.length) % images.length),
    [images.length],
  );

  if (!current) {
    return (
      <p className="media-empty">
        {spanish
          ? "Esta galería no tiene imágenes disponibles."
          : "This gallery has no available images."}
      </p>
    );
  }

  function keyboard(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowLeft") select(index - 1);
    if (event.key === "ArrowRight") select(index + 1);
  }

  return (
    <section
      className="gallery-experience"
      aria-label={`${spanish ? "Galería" : "Gallery"}: ${story.title}`}
      onKeyDown={keyboard}
      tabIndex={0}
    >
      <div className="gallery-stage">
        {/* Source URLs are normalized by the backend media abstraction. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={current.url} alt={`${story.title}, image ${index + 1}`} />
        <button
          type="button"
          className="gallery-previous"
          onClick={() => select(index - 1)}
          aria-label={spanish ? "Imagen anterior" : "Previous image"}
        >
          ←
        </button>
        <button
          type="button"
          className="gallery-next"
          onClick={() => select(index + 1)}
          aria-label={spanish ? "Imagen siguiente" : "Next image"}
        >
          →
        </button>
      </div>
      <div className="gallery-caption" aria-live="polite">
        <span>
          {index + 1} / {images.length}
        </span>
        {current.attribution ? <p>{current.attribution}</p> : null}
      </div>
      <div className="gallery-thumbnails" role="list">
        {images.map((image, imageIndex) => (
          <button
            type="button"
            role="listitem"
            aria-current={imageIndex === index}
            aria-label={`${spanish ? "Ver imagen" : "View image"} ${imageIndex + 1}`}
            onClick={() => select(imageIndex)}
            key={image.id}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageSource(image)} alt="" />
          </button>
        ))}
      </div>
    </section>
  );
}

type ShortCardProps = {
  story: StorySummary;
  portalSlug: string;
  relatedStory?: StorySummary;
  active: boolean;
  registerVideo: (node: HTMLVideoElement | null) => void;
};

function ShortCard({
  story,
  portalSlug,
  relatedStory,
  active,
  registerVideo,
}: ShortCardProps) {
  const card = useRef<HTMLElement>(null);
  const video = useRef<HTMLVideoElement | null>(null);
  const activeRef = useRef(active);
  const playbackRequest = useRef(0);
  const playedAt = useRef<number | null>(null);
  const pendingWatchMilliseconds = useRef(0);
  const sentStart = useRef(false);
  const sentCompletion = useRef(false);
  const sentImpression = useRef(false);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [reacted, setReacted] = useState(false);
  const [saved, setSaved] = useState(false);
  const [notice, setNotice] = useState("");
  const source = story.media.find((item) => item.type === "video");
  const labels =
    story.language === "es"
      ? {
          react: "Me encanta",
          comments: "Comentarios",
          share: "Compartir",
          save: "Guardar",
          fullscreen: "Pantalla completa",
          related: "Relacionado",
          close: "Cerrar",
        }
      : {
          react: "Love",
          comments: "Comments",
          share: "Share",
          save: "Save",
          fullscreen: "Fullscreen",
          related: "Related",
          close: "Close",
        };

  const flushWatchTime = useCallback(() => {
    if (playedAt.current !== null) {
      pendingWatchMilliseconds.current += performance.now() - playedAt.current;
      playedAt.current = null;
    }
    const seconds = Math.floor(pendingWatchMilliseconds.current / 1000);
    if (seconds > 0) {
      pendingWatchMilliseconds.current -= seconds * 1000;
      void event(portalSlug, "watch_time", story.id, { seconds });
    }
  }, [portalSlug, story.id]);

  useEffect(() => {
    if (active && !sentImpression.current) {
      sentImpression.current = true;
      void event(portalSlug, "impression", story.id, { surface: "shorts" });
    }
  }, [active, portalSlug, story.id]);

  useEffect(() => {
    const player = video.current;
    if (!player) return;
    activeRef.current = active;
    const requestId = ++playbackRequest.current;
    if (active) {
      void player.play().then(
        () => {
          if (
            playbackRequest.current === requestId &&
            (!activeRef.current || document.hidden)
          )
            player.pause();
        },
        () => {
          if (playbackRequest.current === requestId && activeRef.current)
            setNotice("Select play to start this Short.");
        },
      );
    } else {
      player.pause();
      flushWatchTime();
    }
    return () => {
      if (playbackRequest.current === requestId) playbackRequest.current += 1;
      player.pause();
      flushWatchTime();
    };
  }, [active, flushWatchTime, portalSlug, story.id]);

  async function action(path: string, method: "PUT" | "DELETE", body?: object) {
    try {
      await communityAction(portalSlug, path, method, body);
      setNotice(method === "PUT" ? "Saved." : "Removed.");
      return true;
    } catch {
      setCommentsOpen(true);
      setNotice("Sign in below to use community features.");
      return false;
    }
  }

  async function share() {
    const url = story.canonical_url;
    try {
      if (navigator.share) await navigator.share({ title: story.title, url });
      else if (navigator.clipboard) await navigator.clipboard.writeText(url);
      else throw new Error("sharing unavailable");
      await event(portalSlug, "share", story.id, { channel: "shorts" });
      setNotice("Share link ready.");
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setNotice("Sharing is unavailable. Open the story to copy its URL.");
    }
  }

  async function fullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (card.current?.requestFullscreen) {
        await card.current.requestFullscreen();
      } else {
        throw new Error("fullscreen unavailable");
      }
    } catch {
      setNotice("Fullscreen is unavailable in this browser.");
    }
  }

  return (
    <article className="short-card" ref={card} data-short-id={story.id}>
      {source ? (
        <video
          ref={(node) => {
            video.current = node;
            registerVideo(node);
          }}
          src={source.url}
          poster={source.thumbnail_url ?? undefined}
          muted
          playsInline
          controls
          preload={active ? "auto" : "metadata"}
          aria-label={`Short video: ${story.title}`}
          onPlay={() => {
            if (!sentStart.current) {
              sentStart.current = true;
              void event(portalSlug, "video_start", story.id, {
                offset_seconds: Math.floor(video.current?.currentTime ?? 0),
              });
            }
          }}
          onPlaying={() => {
            if (activeRef.current) playedAt.current ??= performance.now();
          }}
          onWaiting={flushWatchTime}
          onStalled={flushWatchTime}
          onSeeking={flushWatchTime}
          onPause={flushWatchTime}
          onEnded={() => {
            flushWatchTime();
            if (!sentCompletion.current) {
              sentCompletion.current = true;
              void event(portalSlug, "completion", story.id);
            }
          }}
        >
          Your browser does not support video playback.
        </video>
      ) : (
        <div
          className="short-poster"
          style={{
            backgroundImage: imageSource(story.media[0])
              ? `url(${JSON.stringify(imageSource(story.media[0]))})`
              : undefined,
          }}
          role="img"
          aria-label={story.title}
        />
      )}
      <div className="short-shade" />
      <div className="short-copy">
        <span className="badge">Short</span>
        <h2>
          <Link href={story.url}>{story.title}</Link>
        </h2>
        {story.description ? <p>{story.description}</p> : null}
        {relatedStory ? (
          <Link className="short-related" href={relatedStory.url}>
            {labels.related}: {relatedStory.title} →
          </Link>
        ) : null}
        {notice ? <small role="status">{notice}</small> : null}
      </div>
      <nav className="short-actions" aria-label={`Actions for ${story.title}`}>
        <button
          type="button"
          aria-pressed={reacted}
          onClick={() => {
            const next = !reacted;
            void action(
              `/stories/${encodeURIComponent(story.slug)}/reactions`,
              next ? "PUT" : "DELETE",
              next ? { reaction_type: "love" } : undefined,
            ).then((success) => {
              if (success) setReacted(next);
            });
          }}
        >
          ♥ <span>{labels.react}</span>
        </button>
        <button type="button" onClick={() => setCommentsOpen(!commentsOpen)}>
          ◉ <span>{labels.comments}</span>
        </button>
        <button type="button" onClick={() => void share()}>
          ↗ <span>{labels.share}</span>
        </button>
        <button
          type="button"
          aria-pressed={saved}
          onClick={() => {
            const next = !saved;
            void action(
              `/stories/${encodeURIComponent(story.slug)}/save`,
              next ? "PUT" : "DELETE",
            ).then((success) => {
              if (success) setSaved(next);
            });
          }}
        >
          ★ <span>{labels.save}</span>
        </button>
        <button type="button" onClick={() => void fullscreen()}>
          ⛶ <span>{labels.fullscreen}</span>
        </button>
      </nav>
      {commentsOpen ? (
        <div className="short-comments">
          <button
            type="button"
            className="short-comments-close"
            onClick={() => setCommentsOpen(false)}
          >
            {labels.close}
          </button>
          <CommunityPanel
            portalSlug={portalSlug}
            language={story.language}
            storySlug={story.slug}
            entities={[]}
          />
        </div>
      ) : null}
    </article>
  );
}

export function ShortsFeed({
  items,
  portalSlug,
  nextHref,
}: {
  items: StorySummary[];
  portalSlug: string;
  nextHref?: string;
}) {
  const root = useRef<HTMLDivElement>(null);
  const videos = useRef(new Map<string, HTMLVideoElement>());
  const ratios = useRef(new Map<string, number>());
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const [pageVisible, setPageVisible] = useState(
    typeof document === "undefined" || !document.hidden,
  );
  const effectiveActiveId = items.some((item) => item.id === activeId)
    ? activeId
    : (items[0]?.id ?? "");

  useEffect(() => {
    const visibility = () => setPageVisible(!document.hidden);
    const pageHide = () => setPageVisible(false);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", pageHide);
    window.addEventListener("pageshow", visibility);
    return () => {
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", pageHide);
      window.removeEventListener("pageshow", visibility);
    };
  }, []);

  useEffect(() => {
    const container = root.current;
    if (!container || typeof IntersectionObserver === "undefined") return;
    const observedRatios = ratios.current;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.shortId;
          if (id)
            observedRatios.set(
              id,
              entry.isIntersecting ? entry.intersectionRatio : 0,
            );
        }
        const visible = items
          .map((item, index) => ({
            id: item.id,
            index,
            ratio: observedRatios.get(item.id) ?? 0,
          }))
          .filter((item) => item.ratio >= 0.6)
          .sort(
            (left, right) =>
              right.ratio - left.ratio || left.index - right.index,
          )[0];
        setActiveId(visible?.id ?? "");
      },
      { root: container, threshold: [0.6, 0.8] },
    );
    container
      .querySelectorAll<HTMLElement>("[data-short-id]")
      .forEach((item) => observer.observe(item));
    return () => {
      observer.disconnect();
      observedRatios.clear();
    };
  }, [items]);

  useEffect(() => {
    for (const [id, player] of videos.current) {
      if (id !== effectiveActiveId) player.pause();
    }
  }, [effectiveActiveId]);

  if (!items.length) {
    return <p className="media-empty">No published Shorts are available.</p>;
  }
  return (
    <div className="shorts-feed" ref={root} aria-label="Shorts feed">
      {items.map((story, index) => (
        <ShortCard
          key={story.id}
          story={story}
          portalSlug={portalSlug}
          relatedStory={
            items.length > 1 ? items[(index + 1) % items.length] : undefined
          }
          active={pageVisible && story.id === effectiveActiveId}
          registerVideo={(node) => {
            if (node) videos.current.set(story.id, node);
            else videos.current.delete(story.id);
          }}
        />
      ))}
      {nextHref ? (
        <section className="shorts-end" aria-label="More Shorts">
          <Link href={nextHref}>
            {items[0]?.language === "es" ? "Más Shorts" : "More Shorts"} →
          </Link>
        </section>
      ) : null}
    </div>
  );
}
