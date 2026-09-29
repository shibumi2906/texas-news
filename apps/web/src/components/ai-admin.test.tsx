import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AIAdmin } from "@/components/ai-admin";

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const task = {
  task: "story_summary",
  primary_model: "local:story-summary-v1",
  fallback_models: [],
  allowed_providers: ["local"],
  max_cost: "0.02",
  max_input_tokens: 4000,
  max_output_tokens: 300,
  max_retries: 2,
  timeout_seconds: 10,
  prompt_version: 1,
  is_portal_override: false,
  prompts: [],
};

const overview = {
  portal_slug: "texas",
  available_providers: ["local"],
  provider_credentials: { gateway: false },
  tasks: [task],
  experiments: [],
  usage: {
    window_days: 30,
    executions: 4,
    input_tokens: 420,
    output_tokens: 95,
    estimated_cost: "0.003",
    average_latency_ms: 155,
    errors: 1,
  },
  models: [
    {
      provider: "local",
      model: "story-summary-v1",
      executions: 4,
      estimated_cost: "0.003",
      average_latency_ms: 155,
      errors: 1,
    },
  ],
  errors: [{ task: "story_summary", error_type: "timeout", count: 1 }],
};

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "news_csrf=; Max-Age=0; path=/";
});

describe("AIAdmin", () => {
  it("renders portal task routing, model cost, latency, and error panels", async () => {
    const fetchMock = vi.fn().mockImplementation(() => json(overview));
    vi.stubGlobal("fetch", fetchMock);
    render(<AIAdmin />);

    expect(await screen.findByLabelText("Primary route")).toHaveValue(
      "local:story-summary-v1",
    );
    expect(screen.getAllByText(/0\.003/)).toHaveLength(2);
    expect(screen.getAllByText(/155\s*ms/)).toHaveLength(2);
    expect(screen.getByText("timeout")).toBeInTheDocument();
    expect(screen.queryByText(/api[_ -]?key/i)).not.toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/portals/texas/admin/ai",
    );
  });

  it("authenticates through the existing portal session and clears the password field", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() =>
        json({ detail: { code: "AUTHENTICATION_REQUIRED" } }, 401),
      )
      .mockImplementationOnce(() => json({ user: { role: "admin" } }))
      .mockImplementationOnce(() => json(overview));
    vi.stubGlobal("fetch", fetchMock);
    render(<AIAdmin />);

    const email = await screen.findByLabelText("Email");
    const password = screen.getByLabelText("Password");
    fireEvent.change(email, { target: { value: "admin@example.com" } });
    fireEvent.change(password, { target: { value: "a test password" } });
    fireEvent.submit(password.closest("form")!);

    await screen.findByRole("heading", { name: "AI operations" });
    await waitFor(() =>
      expect(screen.queryByLabelText("Password")).not.toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1][0]).toContain("/auth/login");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });
});
