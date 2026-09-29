import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DistributionAdmin } from "@/components/distribution-admin";

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("DistributionAdmin", () => {
  it("shows portal-scoped ad and notification operations without subscription secrets", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/admin/advertising")) {
        return json({
          portal_slug: "texas",
          enabled: false,
          placements: [
            {
              id: "placement-1",
              code: "story-inline",
              name: "Story inline",
              allowed_content_types: ["article"],
              active: true,
            },
          ],
          campaigns: [
            {
              id: "campaign-1",
              name: "Austin launch",
              status: "active",
              priority: 100,
              targeting: {
                placement_codes: ["story-inline"],
                languages: ["en"],
              },
              creatives: [
                { id: "creative-1", name: "Launch", format: "image" },
              ],
            },
          ],
          impressions: 42,
          clicks: 5,
        });
      }
      return json({
        portal_slug: "texas",
        enabled: true,
        subscriptions: { email: 3, web_push: 2 },
        deliveries: { pending: 1, sent: 9 },
        messages: [
          {
            id: "message-1",
            title: "Tonight in Austin",
            channels: ["email", "web_push"],
            pending: 1,
            sent: 4,
            failed: 0,
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DistributionAdmin />);

    expect(
      await screen.findByRole("heading", { name: "Revenue & reach" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Austin launch")).toBeInTheDocument();
    expect(screen.getByText("Tonight in Austin")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(
      screen.queryByText(/p256dh|subscriber-token|gateway.key/i),
    ).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
