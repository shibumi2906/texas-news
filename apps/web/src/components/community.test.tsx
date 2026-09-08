import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommunityPanel } from "@/components/community";

const entity = {
  id: "00000000-0000-0000-0000-000000000099",
  name: "Austin Artist",
  slug: "austin-artist",
  type: "artist",
};

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("CommunityPanel", () => {
  it("shows public comments and offers authentication to anonymous readers", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementationOnce(() =>
          response({
            items: [
              {
                id: "1",
                user_id: "2",
                parent_id: null,
                author_name: "Reader",
                body: "A Texas perspective",
                status: "visible",
                score: 0,
                created_at: "2026-09-08T12:00:00Z",
              },
            ],
          }),
        )
        .mockImplementationOnce(() => response({}, 401)),
    );
    render(<CommunityPanel storySlug="story" entities={[entity]} />);
    expect(
      screen.getByRole("heading", { name: "Texas talks" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("A Texas perspective")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Join the conversation" }),
    ).toBeInTheDocument();
  });

  it("shows authenticated comment, save, reaction, and follow controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementationOnce(() => response({ items: [] }))
        .mockImplementationOnce(() =>
          response({
            id: "2",
            email: "reader@example.com",
            role: "user",
            display_name: "Reader",
            bio: null,
            preferred_language: "en",
            timezone: "America/Chicago",
          }),
        ),
    );
    render(<CommunityPanel storySlug="story" entities={[entity]} />);
    await waitFor(() =>
      expect(screen.getByText("Signed in as Reader")).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Add a comment")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Like" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Follow Austin Artist" }),
    ).toBeInTheDocument();
  });
});
