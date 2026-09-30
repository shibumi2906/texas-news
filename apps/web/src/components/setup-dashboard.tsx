"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

type Integration = {
  kind: "ai_gateway" | "email" | "web_push";
  enabled: boolean;
  endpoint: string | null;
  provider_name: string | null;
  secret_configured: boolean;
  secret_hint: string | null;
  verified: boolean;
  last_error: string | null;
};

type Overview = {
  portal_slug: string;
  completed: boolean;
  infrastructure: {
    database: boolean;
    redis: boolean;
    secrets_encryption: boolean;
  };
  publisher: {
    canonical_base_url: string;
    publisher_name: string;
    legal_name: string;
    newsroom_email: string;
    funding_disclosure: string;
    logo_url: string | null;
  } | null;
  features: Record<string, boolean>;
  integrations: Integration[];
};

const root = "/api/v1/portals/texas";
const names = {
  ai_gateway: ["AI gateway", "OpenAI-compatible /v1 endpoint"],
  email: ["Email delivery", "Transactional email HTTP gateway"],
  web_push: ["Web push", "Push delivery HTTP gateway"],
} as const;

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
  if (csrf && init?.method && init.method !== "GET")
    headers.set("X-CSRF-Token", decodeURIComponent(csrf));
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
        `Request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export function SetupDashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");

  async function refresh() {
    setData(await api<Overview>("/admin/setup"));
  }

  useEffect(() => {
    let active = true;
    void api<Overview>("/admin/setup")
      .then((result) => active && setData(result))
      .catch((cause: unknown) => {
        if (!active) return;
        const message =
          cause instanceof Error ? cause.message : "Unable to load setup.";
        setError(message === "AUTHENTICATION_REQUIRED" ? "" : message);
      });
    return () => {
      active = false;
    };
  }, []);

  async function run(operation: () => Promise<void>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await operation();
      setNotice(success);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Operation failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <main className="setup-shell">
        <header className="setup-topbar">
          <strong>Texas Entertainment Daily</strong>
          <span>FIRST-RUN SETUP</span>
        </header>
        <section className="setup-login">
          <span className="setup-eyebrow">ADMIN ACCESS REQUIRED</span>
          <h1>Connect your newsroom.</h1>
          <p>Sign in once, then configure services without editing code.</p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void run(async () => {
                await api("/auth/login", {
                  method: "POST",
                  body: JSON.stringify({ email, password }),
                });
                setPassword("");
                await refresh();
              }, "Signed in.");
            }}
          >
            <label>
              Admin email
              <input
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button disabled={busy}>Sign in</button>
          </form>
          <details className="setup-bootstrap">
            <summary>
              Fresh installation? Create the first administrator
            </summary>
            <p>
              This one-time action is available only while the user database is
              has no administrator and setup is incomplete. Production also
              requires the deployment bootstrap token.
            </p>
            <label>
              Bootstrap token (production)
              <input
                type="password"
                value={bootstrapToken}
                onChange={(event) => setBootstrapToken(event.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busy || !email || password.length < 12}
              onClick={() =>
                void run(async () => {
                  await api("/setup/bootstrap-admin", {
                    method: "POST",
                    headers: bootstrapToken
                      ? { "X-Setup-Token": bootstrapToken }
                      : undefined,
                    body: JSON.stringify({
                      email,
                      password,
                      display_name: "Portal owner",
                    }),
                  });
                  setPassword("");
                  await refresh();
                }, "Administrator created.")
              }
            >
              Create owner account
            </button>
          </details>
          {error && error !== "AUTHENTICATION_REQUIRED" ? (
            <p className="setup-error">{error}</p>
          ) : null}
        </section>
      </main>
    );
  }

  const infrastructureReady = Object.values(data.infrastructure).every(Boolean);
  const verified = data.integrations
    .filter((item) => item.enabled)
    .every((item) => item.verified);
  const ready = infrastructureReady && Boolean(data.publisher) && verified;

  return (
    <main className="setup-shell">
      <header className="setup-topbar">
        <Link href="/">Texas Entertainment Daily</Link>
        <span>{data.completed ? "SETUP COMPLETE" : "FIRST-RUN SETUP"}</span>
        <button type="button" onClick={() => void refresh()} disabled={busy}>
          Refresh status
        </button>
      </header>

      <section className="setup-hero">
        <div>
          <span className="setup-eyebrow">
            {data.portal_slug.toUpperCase()} PORTAL
          </span>
          <h1>Launch control.</h1>
          <p>
            Connect infrastructure, identity, AI and delivery from one protected
            workspace.
          </p>
        </div>
        <div className={`setup-score ${ready ? "ready" : ""}`}>
          <strong>{ready ? "Ready" : "Action needed"}</strong>
          <span>
            {data.completed
              ? "Live configuration"
              : "Complete the required checks"}
          </span>
        </div>
      </section>

      {error ? (
        <p className="setup-error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="setup-notice" role="status">
          {notice}
        </p>
      ) : null}

      <section className="setup-status-grid" aria-label="Infrastructure status">
        <Status
          label="PostgreSQL"
          ok={data.infrastructure.database}
          detail="Content and configuration"
        />
        <Status
          label="Redis"
          ok={data.infrastructure.redis}
          detail="Cache and rate limits"
        />
        <Status
          label="Secret vault"
          ok={data.infrastructure.secrets_encryption}
          detail="Encrypted credentials"
        />
      </section>

      <section className="setup-grid">
        <article className="setup-card setup-wide">
          <span className="setup-step">01 · REQUIRED</span>
          <h2>Publisher identity</h2>
          <p>
            Used by canonical URLs, trust pages, structured data and AI
            discovery.
          </p>
          <form
            className="setup-form two-column"
            onSubmit={(event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              void run(async () => {
                const payload: Record<string, FormDataEntryValue | null> =
                  Object.fromEntries(fields);
                if (!payload.logo_url) payload.logo_url = null;
                setData(
                  await api<Overview>("/admin/setup/publisher", {
                    method: "PUT",
                    body: JSON.stringify(payload),
                  }),
                );
              }, "Publisher settings saved.");
            }}
          >
            <label>
              Public site URL
              <input
                name="canonical_base_url"
                type="url"
                defaultValue={
                  data.publisher?.canonical_base_url ?? "http://localhost:3000"
                }
                required
              />
            </label>
            <label>
              Publisher name
              <input
                name="publisher_name"
                defaultValue={
                  data.publisher?.publisher_name ?? "Texas Entertainment Daily"
                }
                required
              />
            </label>
            <label>
              Legal entity
              <input
                name="legal_name"
                defaultValue={data.publisher?.legal_name ?? ""}
                required
              />
            </label>
            <label>
              Newsroom email
              <input
                name="newsroom_email"
                type="email"
                defaultValue={data.publisher?.newsroom_email ?? ""}
                required
              />
            </label>
            <label className="span-two">
              Funding disclosure
              <textarea
                name="funding_disclosure"
                defaultValue={data.publisher?.funding_disclosure ?? ""}
                required
              />
            </label>
            <label className="span-two">
              Logo URL (optional)
              <input
                name="logo_url"
                type="url"
                defaultValue={data.publisher?.logo_url ?? ""}
              />
            </label>
            <button disabled={busy}>Save identity</button>
          </form>
        </article>

        <article className="setup-card setup-wide">
          <span className="setup-step">02 · SERVICES</span>
          <h2>External connections</h2>
          <p>
            Credentials are write-only, encrypted at rest and never returned by
            the API.
          </p>
          <div className="setup-integrations">
            {data.integrations.map((integration) => (
              <IntegrationForm
                key={integration.kind}
                integration={integration}
                busy={busy}
                save={(payload) =>
                  run(async () => {
                    setData(
                      await api<Overview>(
                        `/admin/setup/integrations/${integration.kind}`,
                        { method: "PUT", body: JSON.stringify(payload) },
                      ),
                    );
                  }, `${names[integration.kind][0]} saved.`)
                }
                test={() =>
                  run(async () => {
                    const result = await api<{ ok: boolean; code: string }>(
                      `/admin/setup/integrations/${integration.kind}/test`,
                      { method: "POST", body: "{}" },
                    );
                    await refresh();
                    if (!result.ok)
                      throw new Error(`Connection test failed: ${result.code}`);
                  }, `${names[integration.kind][0]} connected.`)
                }
              />
            ))}
          </div>
        </article>

        <article className="setup-card">
          <span className="setup-step">03 · FEATURES</span>
          <h2>Product switches</h2>
          <form
            className="setup-switches"
            onSubmit={(event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              const payload = Object.fromEntries(
                Object.keys(data.features).map((key) => [key, fields.has(key)]),
              );
              void run(async () => {
                setData(
                  await api<Overview>("/admin/setup/features", {
                    method: "PUT",
                    body: JSON.stringify(payload),
                  }),
                );
              }, "Feature switches saved.");
            }}
          >
            {Object.entries(data.features).map(([key, enabled]) => (
              <label key={key}>
                <input type="checkbox" name={key} defaultChecked={enabled} />
                {key.replaceAll("_", " ")}
              </label>
            ))}
            <button disabled={busy}>Save switches</button>
          </form>
        </article>

        <article className="setup-card">
          <span className="setup-step">04 · OPERATIONS</span>
          <h2>Next controls</h2>
          <ul className="setup-links">
            <li>
              <Link href="/admin/ai">
                AI models, prompts and budgets <b>→</b>
              </Link>
            </li>
            <li>
              <Link href="/admin/distribution">
                Ads and notification campaigns <b>→</b>
              </Link>
            </li>
            <li>
              <Link href="/llms.txt">
                AI discovery manifest <b>→</b>
              </Link>
            </li>
            <li>
              <Link href="/news-sitemap.xml">
                News sitemap <b>→</b>
              </Link>
            </li>
          </ul>
          <p className="setup-help">
            DNS, TLS, CDN, provider accounts and Search Console ownership are
            external to this application. Once created, their site URL and
            gateway credentials are entered here.
          </p>
        </article>
      </section>

      <section className="setup-finish">
        <div>
          <span className="setup-eyebrow">FINAL CHECK</span>
          <h2>
            {data.completed
              ? "Configuration is active."
              : "Ready to open the newsroom?"}
          </h2>
        </div>
        <button
          disabled={busy || !ready}
          onClick={() =>
            void run(async () => {
              setData(
                await api<Overview>("/admin/setup/complete", {
                  method: "POST",
                  body: "{}",
                }),
              );
            }, "Setup completed. The public site is ready.")
          }
        >
          {data.completed ? "Revalidate setup" : "Complete setup"}
        </button>
      </section>
    </main>
  );
}

function Status({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <article>
      <span className={ok ? "status-dot ok" : "status-dot"} />
      <div>
        <strong>{label}</strong>
        <small>
          {ok ? "Connected" : "Not ready"} · {detail}
        </small>
      </div>
    </article>
  );
}

function IntegrationForm({
  integration,
  busy,
  save,
  test,
}: {
  integration: Integration;
  busy: boolean;
  save: (payload: unknown) => Promise<void>;
  test: () => Promise<void>;
}) {
  return (
    <form
      className="integration-row"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        void save({
          enabled: fields.has("enabled"),
          endpoint: fields.get("endpoint") || null,
          provider_name: fields.get("provider_name") || null,
          secret: fields.get("secret") || null,
        });
      }}
    >
      <div className="integration-title">
        <span className={`status-dot ${integration.verified ? "ok" : ""}`} />
        <div>
          <strong>{names[integration.kind][0]}</strong>
          <small>{names[integration.kind][1]}</small>
        </div>
      </div>
      <label className="inline-check">
        <input
          name="enabled"
          type="checkbox"
          defaultChecked={integration.enabled}
        />
        Enabled
      </label>
      <label>
        Endpoint
        <input
          name="endpoint"
          type="url"
          defaultValue={integration.endpoint ?? ""}
          placeholder="https://gateway.example/v1"
        />
      </label>
      <label>
        Provider name
        <input
          name="provider_name"
          defaultValue={integration.provider_name ?? ""}
          placeholder="Provider"
        />
      </label>
      <label>
        API key
        <input
          name="secret"
          type="password"
          autoComplete="new-password"
          placeholder={integration.secret_hint ?? "Enter credential"}
        />
        <small>
          {integration.secret_configured
            ? `Stored ${integration.secret_hint}`
            : "Not stored"}
        </small>
      </label>
      <div className="integration-actions">
        <button disabled={busy}>Save</button>
        <button
          className="secondary"
          type="button"
          disabled={busy || !integration.enabled}
          onClick={() => void test()}
        >
          Test
        </button>
      </div>
      {integration.last_error ? (
        <small className="integration-error">
          Last test: {integration.last_error}
        </small>
      ) : null}
    </form>
  );
}
