import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AiAssistant } from "@/components/ai-assistant";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  let next = 0;
  vi.stubGlobal("crypto", { randomUUID: () => `uuid-${++next}` });
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => vi.unstubAllGlobals());

function answer(overrides = {}) {
  return {
    answer: "The Mavericks announced a concert.",
    status: "answered",
    insufficient_evidence: false,
    generated: true,
    fallback_used: false,
    sources: [
      { content_id: "1", title: "Mavericks story", url: "/story/mavericks" },
    ],
    metadata: { timezone: "America/Chicago", ranking_authoritative: false },
    ...overrides,
  };
}

describe("AiAssistant", () => {
  it("asks a grounded search question and renders source links", async () => {
    fetchMock.mockResolvedValue(Response.json(answer()));
    render(<AiAssistant />);
    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "What happened with the Mavericks?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText("The Mavericks announced a concert."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Mavericks story" }),
    ).toHaveAttribute("href", "/story/mavericks");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/portals/texas/ai/search",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("supports both deterministic quick briefs and explains trending ownership", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        answer({
          metadata: {
            timezone: "America/Chicago",
            ranking_authoritative: true,
          },
        }),
      ),
    );
    render(<AiAssistant />);
    fireEvent.click(screen.getByRole("button", { name: "What's trending?" }));
    expect(
      await screen.findByText(/Ranking comes from the platform trending feed/),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/portals/texas/ai/trending",
    );
  });

  it("loads the current-day brief from the dedicated today endpoint", async () => {
    fetchMock.mockResolvedValue(Response.json(answer()));
    render(<AiAssistant />);
    fireEvent.click(
      screen.getByRole("button", { name: "What happened today?" }),
    );
    expect(
      await screen.findByText("The Mavericks announced a concert."),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/portals/texas/ai/today");
  });

  it("keeps story questions on the story endpoint and handles insufficient evidence", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        answer({
          answer:
            "The platform does not have enough published information to answer that.",
          status: "insufficient_evidence",
          insufficient_evidence: true,
          sources: [],
        }),
      ),
    );
    render(<AiAssistant storySlug="story-one" />);
    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "Who confirmed it?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText(/not enough published platform evidence/),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/portals/texas/stories/story-one/ai-question",
    );
    expect(
      screen.queryByRole("button", { name: "What's trending?" }),
    ).not.toBeInTheDocument();
  });

  it("shows the rate-limit state", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 429 }));
    render(<AiAssistant />);
    fireEvent.click(
      screen.getByRole("button", { name: "What happened today?" }),
    );
    expect(await screen.findByText(/Too many AI requests/)).toBeInTheDocument();
  });

  it("shows a safe unavailable state when a feature is disabled", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 404 }));
    render(<AiAssistant />);
    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "What happened?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText("AI answers are temporarily unavailable."),
    ).toBeInTheDocument();
  });
});
