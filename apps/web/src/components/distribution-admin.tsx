"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

type Placement = {
  id: string;
  code: string;
  name: string;
  allowed_content_types: string[];
  active: boolean;
};

type Campaign = {
  id: string;
  name: string;
  status: string;
  priority: number;
  targeting: { placement_codes: string[]; languages: string[] };
  creatives: Array<{ id: string; name: string; format: string }>;
};

type AdvertisingOverview = {
  portal_slug: string;
  enabled: boolean;
  placements: Placement[];
  campaigns: Campaign[];
  impressions: number;
  clicks: number;
};

type NotificationOverview = {
  portal_slug: string;
  enabled: boolean;
  subscriptions: Record<string, number>;
  deliveries: Record<string, number>;
  messages: Array<{
    id: string;
    title: string;
    channels: string[];
    pending: number;
    sent: number;
    failed: number;
  }>;
};

const root = "/api/v1/portals/texas";

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith("news_csrf="))
    ?.split("=")
    .slice(1)
    .join("=");
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const csrf = csrfToken();
  if (csrf && init?.method && init.method !== "GET") {
    headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(`${root}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const result = (await response.json().catch(() => null)) as {
      detail?: { code?: string; message?: string };
    } | null;
    throw new Error(
      result?.detail?.message ??
        result?.detail?.code ??
        `HTTP ${response.status}`,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function DistributionAdmin() {
  const [advertising, setAdvertising] = useState<AdvertisingOverview | null>(
    null,
  );
  const [notifications, setNotifications] =
    useState<NotificationOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function refresh() {
    setError("");
    const [ads, notices] = await Promise.all([
      api<AdvertisingOverview>("/admin/advertising"),
      api<NotificationOverview>("/admin/notifications"),
    ]);
    setAdvertising(ads);
    setNotifications(notices);
  }

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      api<AdvertisingOverview>("/admin/advertising"),
      api<NotificationOverview>("/admin/notifications"),
    ])
      .then(([ads, notices]) => {
        if (!cancelled) {
          setAdvertising(ads);
          setNotifications(notices);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to load admin data.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setPassword("");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function mutate(path: string, body: unknown, method = "POST") {
    setBusy(true);
    setError("");
    try {
      await api(path, { method, body: JSON.stringify(body) });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!advertising || !notifications) {
    return (
      <main className="distribution-admin">
        <header>
          <Link href="/">Texas Entertainment Daily</Link>
          <span>ADMIN / DISTRIBUTION</span>
        </header>
        <section className="distribution-login">
          <p className="distribution-kicker">SECURE WORKSPACE</p>
          <h1>Revenue &amp; reach</h1>
          <form onSubmit={login}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button disabled={busy}>Sign in</button>
          </form>
          {error ? <p role="alert">{error}</p> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="distribution-admin">
      <header>
        <Link href="/">Texas Entertainment Daily</Link>
        <span>ADMIN / DISTRIBUTION</span>
        <button onClick={() => void refresh()}>Refresh</button>
      </header>
      <section className="distribution-title">
        <p className="distribution-kicker">PORTAL-SCOPED CONTROL</p>
        <h1>Revenue &amp; reach</h1>
        <p>
          Deterministic ad delivery and consent-based notification operations.
        </p>
      </section>
      {error ? (
        <p className="distribution-error" role="alert">
          {error}
        </p>
      ) : null}
      <section
        className="distribution-metrics"
        aria-label="Distribution metrics"
      >
        <Metric
          label="Ad serving"
          value={advertising.enabled ? "Enabled" : "Disabled"}
        />
        <Metric label="Impressions" value={advertising.impressions} />
        <Metric label="Clicks" value={advertising.clicks} />
        <Metric
          label="Subscribers"
          value={Object.values(notifications.subscriptions).reduce(
            (sum, value) => sum + value,
            0,
          )}
        />
        <Metric
          label="Notification delivery"
          value={notifications.enabled ? "Enabled" : "Disabled"}
        />
      </section>

      <section className="distribution-grid">
        <article>
          <p className="distribution-kicker">AD INVENTORY</p>
          <h2>Placements</h2>
          <ul>
            {advertising.placements.map((item) => (
              <li key={item.id}>
                <strong>{item.name}</strong>
                <span>{item.code}</span>
              </li>
            ))}
          </ul>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              void mutate("/admin/advertising/placements", {
                code: fields.get("code"),
                name: fields.get("name"),
                allowed_content_types: ["article", "gallery", "video", "short"],
                active: true,
              });
              event.currentTarget.reset();
            }}
          >
            <label>
              Placement code
              <input name="code" placeholder="story-inline" required />
            </label>
            <label>
              Name
              <input name="name" placeholder="Story inline" required />
            </label>
            <button disabled={busy}>Add placement</button>
          </form>
        </article>

        <article>
          <p className="distribution-kicker">CAMPAIGNS</p>
          <h2>Targeting &amp; creative</h2>
          <ul>
            {advertising.campaigns.map((item) => (
              <li key={item.id}>
                <strong>{item.name}</strong>
                <span>
                  {item.status} ·{" "}
                  {item.targeting.languages.join(", ") || "all languages"}
                </span>
              </li>
            ))}
          </ul>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              const placement = String(fields.get("placement"));
              void mutate("/admin/advertising/campaigns", {
                name: fields.get("name"),
                status: "active",
                priority: 100,
                starts_at: new Date().toISOString(),
                ends_at: null,
                targeting: {
                  placement_codes: [placement],
                  geography_ids: [],
                  languages: ["en"],
                  category_ids: [],
                  content_types: [],
                },
                creatives: [
                  {
                    name: `${String(fields.get("name"))} creative`,
                    format: "image",
                    asset_url: fields.get("asset_url"),
                    click_url: fields.get("click_url"),
                    alt_text: fields.get("alt_text"),
                    active: true,
                  },
                ],
              });
              event.currentTarget.reset();
            }}
          >
            <label>
              Campaign name
              <input name="name" required />
            </label>
            <label>
              Placement
              <select name="placement" required>
                <option value="">Select placement</option>
                {advertising.placements.map((item) => (
                  <option key={item.id} value={item.code}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Creative URL
              <input name="asset_url" type="url" required />
            </label>
            <label>
              Click URL
              <input name="click_url" type="url" required />
            </label>
            <label>
              Alt text
              <input name="alt_text" required />
            </label>
            <button disabled={busy || advertising.placements.length === 0}>
              Launch campaign
            </button>
          </form>
        </article>

        <article>
          <p className="distribution-kicker">NOTIFICATIONS</p>
          <h2>Delivery queue</h2>
          <p>
            Email {notifications.subscriptions.email ?? 0} · Web push{" "}
            {notifications.subscriptions.web_push ?? 0}
          </p>
          <ul>
            {notifications.messages.map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong>
                <span>
                  {item.sent} sent · {item.pending} pending · {item.failed}{" "}
                  failed
                </span>
              </li>
            ))}
          </ul>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              void mutate("/admin/notifications/messages", {
                title: fields.get("title"),
                body: fields.get("body"),
                url: fields.get("url"),
                content_id: null,
                channels: ["email", "web_push"],
              });
              event.currentTarget.reset();
            }}
          >
            <label>
              Title
              <input name="title" required />
            </label>
            <label>
              Message
              <textarea name="body" required />
            </label>
            <label>
              Portal URL
              <input name="url" defaultValue="/" required />
            </label>
            <button disabled={busy || !notifications.enabled}>
              Queue notification
            </button>
          </form>
        </article>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
