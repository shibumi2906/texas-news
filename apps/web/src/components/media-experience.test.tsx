import { StrictMode } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GalleryExperience, ShortsFeed } from "@/components/media-experience";
import type { Media, Portal, Story, StorySummary } from "@/lib/public-api";

const portal: Portal = {
  name: "Texas Entertainment Daily",
  slug: "texas",
  domain: "texas.example",
  timezone: "America/Chicago",
  default_language: "en",
  supported_languages: ["en", "es"],
  canonical_url: "https://texas.example",
  branding: {},
  categories: [],
};

function media(id: string, position: number, type = "image"): Media {
  return {
    id,
    type,
    url: `https://media.example/${id}`,
    thumbnail_url: null,
    mime_type: type === "video" ? "video/mp4" : "image/jpeg",
    width: 720,
    height: 1280,
    duration: type === "video" ? 30 : null,
    position,
    attribution: `Caption ${position}`,
    provider: null,
  };
}

function summary(id: string): StorySummary {
  return {
    id,
    slug: `short-${id}`,
    url: `/story/short-${id}`,
    canonical_url: `https://texas.example/story/short-${id}`,
    language: "en",
    alternates: { en: `https://texas.example/story/short-${id}` },
    content_type: "short",
    title: `Texas Short ${id}`,
    subtitle: null,
    description: "A vertical Texas video",
    author: "Newsroom",
    published_at: "2026-09-11T10:00:00Z",
    updated_at: "2026-09-11T10:00:00Z",
    source: null,
    categories: [],
    geography: [],
    media: [media(`video-${id}`, 0, "video")],
  };
}

describe("gallery experience", () => {
  it("navigates an ordered gallery with buttons and keyboard", () => {
    const item: Story = {
      ...summary("gallery"),
      content_type: "gallery",
      title: "Texas gallery",
      media: [media("one", 0), media("two", 1), media("three", 2)],
      portal,
      body: null,
      original_url: null,
      entities: [],
      seo: {},
      related: [],
    };
    render(<GalleryExperience story={item} />);
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next image" }));
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("region", { name: /Gallery/ }), {
      key: "ArrowLeft",
    });
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });
});

describe("Shorts experience", () => {
  let observerCallback: IntersectionObserverCallback;
  const play = vi.fn(() => Promise.resolve());
  const pause = vi.fn();
  const fetchMock = vi.fn<
    (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  >(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response),
  );

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(pause);
    class Observer {
      constructor(callback: IntersectionObserverCallback) {
        observerCallback = callback;
      }
      observe = vi.fn();
      disconnect = vi.fn();
      unobserve = vi.fn();
      takeRecords = vi.fn(() => []);
      root = null;
      rootMargin = "0px";
      thresholds = [0.6, 0.8];
    }
    vi.stubGlobal("IntersectionObserver", Observer);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("autoplays one active Short, pauses it on navigation and records playback", async () => {
    render(
      <ShortsFeed items={[summary("1"), summary("2")]} portalSlug="texas" />,
    );
    const videos = screen.getAllByLabelText(
      /Short video/,
    ) as HTMLVideoElement[];
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));

    act(() => {
      observerCallback(
        [
          {
            target: videos[1].closest("article") as Element,
            isIntersecting: true,
            intersectionRatio: 0.9,
          } as IntersectionObserverEntry,
        ],
        {} as IntersectionObserver,
      );
    });
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    expect(pause).toHaveBeenCalled();

    fireEvent.play(videos[1]);
    fireEvent.ended(videos[1]);
    await waitFor(() => {
      const payloads = fetchMock.mock.calls
        .map((call) => JSON.parse(String(call[1]?.body ?? "{}")))
        .filter((payload) => payload.event_type);
      expect(
        payloads.some((payload) => payload.event_type === "video_start"),
      ).toBe(true);
      expect(
        payloads.some((payload) => payload.event_type === "completion"),
      ).toBe(true);
      expect(
        payloads
          .filter((payload) =>
            ["video_start", "completion"].includes(payload.event_type),
          )
          .every((payload) => payload.content_id === "2"),
      ).toBe(true);
    });
  });

  it("keeps the highest visible Short active and pauses playback when the page hides", async () => {
    let hidden = false;
    vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
    render(
      <ShortsFeed
        items={[summary("1"), summary("2"), summary("3")]}
        portalSlug="texas"
      />,
    );
    const cards = screen
      .getAllByLabelText(/Short video/)
      .map((video) => video.closest("article") as Element);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));

    act(() => {
      observerCallback(
        [
          {
            target: cards[1],
            isIntersecting: true,
            intersectionRatio: 0.75,
          } as IntersectionObserverEntry,
        ],
        {} as IntersectionObserver,
      );
    });
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));

    act(() => {
      observerCallback(
        [
          {
            target: cards[2],
            isIntersecting: true,
            intersectionRatio: 0.61,
          } as IntersectionObserverEntry,
        ],
        {} as IntersectionObserver,
      );
    });
    expect(play).toHaveBeenCalledTimes(2);

    hidden = true;
    fireEvent(document, new Event("visibilitychange"));
    await waitFor(() => expect(pause).toHaveBeenCalled());
  });

  it("ignores stale play completion during Strict Mode effect replay", async () => {
    const resolvers: Array<() => void> = [];
    play.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolvers.push(resolve);
        }),
    );
    render(
      <StrictMode>
        <ShortsFeed items={[summary("1")]} portalSlug="texas" />
      </StrictMode>,
    );
    await waitFor(() => expect(resolvers.length).toBe(2));
    const pausesBeforeResolution = pause.mock.calls.length;
    await act(async () => resolvers[0]());
    expect(pause).toHaveBeenCalledTimes(pausesBeforeResolution);
    await act(async () => resolvers[1]());
    expect(pause).toHaveBeenCalledTimes(pausesBeforeResolution);
  });

  it("counts active playback time once and does not duplicate impressions or starts", async () => {
    const now = vi.spyOn(performance, "now");
    now.mockReturnValue(1000);
    render(<ShortsFeed items={[summary("1")]} portalSlug="texas" />);
    const video = screen.getByLabelText(/Short video/) as HTMLVideoElement;
    fireEvent.play(video);
    fireEvent.playing(video);
    now.mockReturnValue(3600);
    fireEvent.waiting(video);
    fireEvent.play(video);

    await waitFor(() => {
      const payloads = fetchMock.mock.calls.map((call) =>
        JSON.parse(String(call[1]?.body ?? "{}")),
      );
      expect(
        payloads.filter((payload) => payload.event_type === "impression"),
      ).toHaveLength(1);
      expect(
        payloads.filter((payload) => payload.event_type === "video_start"),
      ).toHaveLength(1);
      expect(
        payloads.filter((payload) => payload.event_type === "watch_time"),
      ).toEqual([
        expect.objectContaining({
          content_id: "1",
          properties: { seconds: 2 },
        }),
      ]);
    });
  });

  it("uses the active portal, real related item, toggles actions and handles fullscreen failure", async () => {
    render(
      <ShortsFeed items={[summary("1"), summary("2")]} portalSlug="dallas" />,
    );
    expect(
      screen.getAllByRole("button", { name: /Love/ })[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Comments/ })[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Share/ })[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Save/ })[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Fullscreen/ })[0],
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Related/ })[0]).toHaveAttribute(
      "href",
      "/story/short-2",
    );

    const love = screen.getAllByRole("button", { name: /Love/ })[0];
    const save = screen.getAllByRole("button", { name: /Save/ })[0];
    fireEvent.click(love);
    fireEvent.click(save);
    await waitFor(() => expect(love).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(love);
    await waitFor(() => expect(love).toHaveAttribute("aria-pressed", "false"));
    expect(
      fetchMock.mock.calls
        .map((call) => String(call[0]))
        .filter((url) => url.includes("/community/"))
        .every((url) => url.includes("/portals/dallas/")),
    ).toBe(true);
    expect(
      fetchMock.mock.calls
        .map((call) => String(call[0]))
        .filter((url) => url.includes("/analytics/"))
        .every((url) => url.includes("/portals/dallas/")),
    ).toBe(true);

    const firstCard = love.closest("article") as HTMLElement;
    Object.defineProperty(firstCard, "requestFullscreen", {
      configurable: true,
      value: vi.fn(() => Promise.reject(new Error("unsupported"))),
    });
    fireEvent.click(screen.getAllByRole("button", { name: /Fullscreen/ })[0]);
    expect(
      await screen.findByText("Fullscreen is unavailable in this browser."),
    ).toBeInTheDocument();
  });
});
