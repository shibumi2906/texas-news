import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AiStorySummary } from "@/components/ai-story-summary";

afterEach(() => vi.unstubAllGlobals());

describe("AiStorySummary", () => {
  it("loads only on demand and labels generated content", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          bullets: ["First verified point.", "Second verified point."],
          generated: true,
          fallback_used: false,
          cached: false,
          sources: [
            {
              title: "Story",
              canonical_url: "https://texas.example/story/story",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<AiStorySummary storySlug="story" language="en" />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Summarize this story" }),
    );
    expect(
      await screen.findByText("First verified point."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/AI-generated from this published story only/),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/portals/texas/stories/story/ai-summary?language=en",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("shows a safe error without replacing the story", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 503 })),
    );
    render(<AiStorySummary storySlug="story" language="en" />);
    fireEvent.click(
      screen.getByRole("button", { name: "Summarize this story" }),
    );
    expect(
      await screen.findByText("The summary is temporarily unavailable."),
    ).toBeInTheDocument();
  });

  it("labels deterministic fallback without presenting it as AI-generated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            bullets: ["Extracted point one.", "Extracted point two."],
            generated: false,
            fallback_used: true,
            cached: false,
            sources: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    render(<AiStorySummary storySlug="story" language="en" />);
    fireEvent.click(
      screen.getByRole("button", { name: "Summarize this story" }),
    );
    expect(
      await screen.findByText(
        /Deterministic fallback from this published story only/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/AI-generated from/)).not.toBeInTheDocument();
  });
});
