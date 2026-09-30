import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SetupDashboard } from "@/components/setup-dashboard";

describe("SetupDashboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows infrastructure, write-only integrations, and operational links", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          portal_slug: "texas",
          completed: false,
          infrastructure: {
            database: true,
            redis: true,
            secrets_encryption: true,
          },
          publisher: null,
          features: {
            ai_search: true,
            ai_chat: true,
            advertising: false,
            notifications: false,
            community: true,
            recommendations: true,
          },
          integrations: [
            {
              kind: "ai_gateway",
              enabled: true,
              endpoint: "https://ai.example/v1",
              provider_name: "Gateway",
              secret_configured: true,
              secret_hint: "••••1234",
              verified: true,
              last_error: null,
            },
            {
              kind: "email",
              enabled: false,
              endpoint: null,
              provider_name: null,
              secret_configured: false,
              secret_hint: null,
              verified: false,
              last_error: null,
            },
            {
              kind: "web_push",
              enabled: false,
              endpoint: null,
              provider_name: null,
              secret_configured: false,
              secret_hint: null,
              verified: false,
              last_error: null,
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<SetupDashboard />);

    expect(
      await screen.findByRole("heading", { name: "Launch control." }),
    ).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Stored ••••1234")).toBeInTheDocument();
    expect(screen.queryByText(/Bearer/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /AI models, prompts and budgets/ }),
    ).toHaveAttribute("href", "/admin/ai");
  });
});
