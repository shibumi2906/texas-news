import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import SearchPage from "./page";
import { type SearchPageData } from "@/lib/public-api";
const fetchMock = vi.fn();
const data: SearchPageData = {
  portal: {
    name: "Texas",
    slug: "texas",
    domain: "texas.example",
    timezone: "America/Chicago",
    default_language: "en",
    canonical_url: "https://texas.example",
    branding: {},
    categories: [{ name: "Sports", slug: "sports" }],
  },
  query: "Mavericks",
  language: "en",
  next_cursor: "opaque-next",
  items: [
    {
      id: "1",
      slug: "stable-slug",
      url: "/story/stable-slug",
      canonical_url: "https://texas.example/story/stable-slug",
      content_type: "article",
      title: "Editorial Mavericks headline",
      subtitle: null,
      description: "Editorial description",
      author: null,
      published_at: "2026-09-05T12:00:00Z",
      updated_at: "2026-09-05T12:00:00Z",
      source: null,
      categories: [],
      geography: [],
      media: [],
    },
  ],
};
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
describe("Search page", () => {
  it("renders effective values and preserves filters in next-page links", async () => {
    fetchMock.mockResolvedValue(Response.json(data));
    render(
      await SearchPage({
        searchParams: Promise.resolve({
          q: "Mavericks",
          category: "sports",
          geography: "austin",
          entity: "Mavs",
          date_from: "2026-09-01",
        }),
      }),
    );
    expect(screen.getByRole("search")).toHaveAttribute("action", "/search");
    expect(screen.getByLabelText("Keywords")).toHaveValue("Mavericks");
    expect(screen.getByLabelText("Entity name or slug")).toHaveValue("Mavs");
    expect(
      screen.getByRole("heading", { name: "Editorial Mavericks headline" }),
    ).toBeInTheDocument();
    const next = new URL(
      screen.getByRole("link", { name: "Next results" }).getAttribute("href")!,
      "https://texas.example",
    );
    expect(next.searchParams.get("cursor")).toBe("opaque-next");
    expect(next.searchParams.get("category")).toBe("sports");
    expect(next.searchParams.get("date_from")).toBe("2026-09-01");
    expect(new URL(fetchMock.mock.calls[0][0]).searchParams.get("limit")).toBe(
      "12",
    );
  });
  it("shows empty results", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        ...data,
        items: [],
        next_cursor: null,
      }),
    );
    render(
      await SearchPage({ searchParams: Promise.resolve({ q: "nothing" }) }),
    );
    expect(screen.getByText(/No stories found/)).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Next results" }),
    ).not.toBeInTheDocument();
  });
  it.each([400, 404, 422, 503])(
    "handles API error %s and offers a clean restart",
    async (status) => {
      fetchMock.mockResolvedValue(new Response(null, { status }));
      render(
        await SearchPage({
          searchParams: Promise.resolve({ q: "Mavericks", cursor: "stale" }),
        }),
      );
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Restart search" }),
      ).toHaveAttribute("href", "/search?q=Mavericks");
    },
  );
});
