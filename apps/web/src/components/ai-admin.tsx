"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

type PromptVersion = {
  id: string;
  version: number;
  status: string;
  template: string;
  notes: string | null;
  created_at: string;
  created_by: string;
  scope: "portal" | "system";
};

type Task = {
  task: string;
  primary_model: string;
  fallback_models: string[];
  allowed_providers: string[];
  max_cost: string;
  max_input_tokens: number;
  max_output_tokens: number;
  max_retries: number;
  timeout_seconds: number;
  prompt_version: number;
  is_portal_override: boolean;
  prompts: PromptVersion[];
};

type Experiment = {
  id: string | null;
  task: string;
  name: string | null;
  prompt_version_a_id: string | null;
  prompt_version_b_id: string | null;
  variant_b_percent: number | null;
  status: string;
};

type Overview = {
  portal_slug: string;
  available_providers: string[];
  provider_credentials: Record<string, boolean>;
  tasks: Task[];
  experiments: Experiment[];
  usage: Record<string, string | number>;
  models: Array<Record<string, string | number | null>>;
  errors: Array<Record<string, string | number | null>>;
};

const apiRoot = "/api/v1/portals/texas";

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
  const response = await fetch(`${apiRoot}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: { message?: string; code?: string };
    } | null;
    throw new Error(
      payload?.detail?.message ??
        payload?.detail?.code ??
        `HTTP ${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export function AIAdmin() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function refresh() {
    setError("");
    try {
      setData(await api<Overview>("/admin/ai"));
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to load AI admin.",
      );
    }
  }

  useEffect(() => {
    let cancelled = false;
    void api<Overview>("/admin/ai")
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(
            cause instanceof Error ? cause.message : "Unable to load AI admin.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
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

  async function save(path: string, body: unknown) {
    setBusy(true);
    setError("");
    try {
      setData(
        await api<Overview>(path, {
          method: path.includes("experiments/") ? "PUT" : "PATCH",
          body: JSON.stringify(body),
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createPrompt(task: string, form: HTMLFormElement) {
    const fields = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await api(`/admin/ai/tasks/${task}/prompts`, {
        method: "POST",
        body: JSON.stringify({
          template: fields.get("template"),
          notes: fields.get("notes") || null,
        }),
      });
      form.reset();
      await refresh();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Prompt creation failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <main className="ai-admin-shell">
        <header className="ai-admin-header">
          <Link href="/">Texas Entertainment Daily</Link>
          <span>ADMIN / AI CONTROL</span>
        </header>
        <section className="ai-admin-login">
          <p className="ai-admin-kicker">SECURE WORKSPACE</p>
          <h1>AI operations</h1>
          <p>
            Sign in with a portal admin account to manage models and prompts.
          </p>
          <form onSubmit={login}>
            <label>
              Email
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
            <button disabled={busy} type="submit">
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          {error ? (
            <p className="ai-admin-error" role="alert">
              {error}
            </p>
          ) : null}
        </section>
      </main>
    );
  }

  const usage = data.usage;
  return (
    <main className="ai-admin-shell">
      <header className="ai-admin-header">
        <Link href="/">Texas Entertainment Daily</Link>
        <span>ADMIN / AI CONTROL</span>
        <button type="button" onClick={() => void refresh()}>
          Refresh
        </button>
      </header>
      <section className="ai-admin-title">
        <div>
          <p className="ai-admin-kicker">
            {data.portal_slug.toUpperCase()} PORTAL · LAST 30 DAYS
          </p>
          <h1>AI operations</h1>
          <p>
            Provider routing, prompt releases, experiments and runtime health.
          </p>
        </div>
        <div className="ai-admin-provider-state">
          <span>Available providers</span>
          <strong>
            {data.available_providers.join(" · ") || "None configured"}
          </strong>
          <small>
            Gateway credentials:{" "}
            {data.provider_credentials.gateway
              ? "configured"
              : "not configured"}
          </small>
        </div>
      </section>
      {error ? (
        <p className="ai-admin-error" role="alert">
          {error}
        </p>
      ) : null}
      <section className="ai-admin-metrics" aria-label="AI usage summary">
        <Metric label="Executions" value={usage.executions ?? 0} />
        <Metric
          label="Estimated cost"
          value={`$${usage.estimated_cost ?? "0"}`}
        />
        <Metric
          label="Avg latency"
          value={`${Math.round(Number(usage.average_latency_ms ?? 0))} ms`}
        />
        <Metric label="Errors" value={usage.errors ?? 0} />
        <Metric
          label="Tokens in / out"
          value={`${usage.input_tokens ?? 0} / ${usage.output_tokens ?? 0}`}
        />
      </section>
      <section className="ai-admin-section">
        <div className="ai-admin-section-heading">
          <div>
            <p className="ai-admin-kicker">CONFIGURATION</p>
            <h2>Tasks and routing</h2>
          </div>
          <p>Changes apply to this portal through the Phase 10 AI service.</p>
        </div>
        <div className="ai-admin-task-grid">
          {data.tasks.map((task) => (
            <TaskCard
              key={task.task}
              task={task}
              providers={data.available_providers}
              experiment={data.experiments.find(
                (item) => item.task === task.task,
              )}
              busy={busy}
              save={save}
              createPrompt={createPrompt}
              activatePrompt={async (versionId) => {
                setBusy(true);
                try {
                  setData(
                    await api<Overview>(
                      `/admin/ai/tasks/${task.task}/prompts/${versionId}/activate`,
                      { method: "POST", body: JSON.stringify({}) },
                    ),
                  );
                  setError("");
                } catch (cause) {
                  setError(
                    cause instanceof Error
                      ? cause.message
                      : "Activation failed.",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            />
          ))}
        </div>
      </section>
      <section className="ai-admin-section ai-admin-lower-grid">
        <div>
          <p className="ai-admin-kicker">MODEL HEALTH</p>
          <h2>Models</h2>
          {data.models.length ? (
            <div className="ai-admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Provider / model</th>
                    <th>Runs</th>
                    <th>Cost</th>
                    <th>Latency</th>
                    <th>Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {data.models.map((model, index) => (
                    <tr key={`${model.provider}-${model.model}-${index}`}>
                      <td>
                        {model.provider}
                        <br />
                        <strong>{model.model}</strong>
                      </td>
                      <td>{model.executions}</td>
                      <td>${model.estimated_cost}</td>
                      <td>{Math.round(Number(model.average_latency_ms))} ms</td>
                      <td>{model.errors}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="ai-admin-empty">
              No recorded executions in this period.
            </p>
          )}
        </div>
        <div>
          <p className="ai-admin-kicker">FAILURE MONITOR</p>
          <h2>Errors</h2>
          {data.errors.length ? (
            <ul className="ai-admin-error-list">
              {data.errors.map((item, index) => (
                <li key={`${item.task}-${item.error_type}-${index}`}>
                  <strong>{item.task}</strong>
                  <span>{item.error_type ?? "unknown"}</span>
                  <b>{item.count}</b>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ai-admin-empty">No errors recorded in this period.</p>
          )}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>30 day window</small>
    </article>
  );
}

function TaskCard({
  task,
  providers,
  experiment,
  busy,
  save,
  createPrompt,
  activatePrompt,
}: {
  task: Task;
  providers: string[];
  experiment?: Experiment;
  busy: boolean;
  save: (path: string, body: unknown) => Promise<void>;
  createPrompt: (task: string, form: HTMLFormElement) => Promise<void>;
  activatePrompt: (id: string) => Promise<void>;
}) {
  const [fallbacks, setFallbacks] = useState(task.fallback_models.join(", "));
  const [providersText, setProvidersText] = useState(
    task.allowed_providers.join(", "),
  );
  const [promptA, setPromptA] = useState(experiment?.prompt_version_a_id ?? "");
  const [promptB, setPromptB] = useState(experiment?.prompt_version_b_id ?? "");
  const activePrompts = task.prompts.filter(
    (prompt) => prompt.status === "active",
  );
  return (
    <article className="ai-admin-task-card">
      <header>
        <div>
          <p className="ai-admin-kicker">AI TASK</p>
          <h3>{task.task.replaceAll("_", " ")}</h3>
        </div>
        <span
          className={
            task.is_portal_override ? "ai-admin-tag override" : "ai-admin-tag"
          }
        >
          {task.is_portal_override ? "portal override" : "env defaults"}
        </span>
      </header>
      <form
        className="ai-admin-config-form"
        onSubmit={(event) => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          void save(`/admin/ai/tasks/${task.task}`, {
            primary_model: fields.get("primary_model"),
            fallback_models: fallbacks
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean),
            allowed_providers: providersText
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean),
            max_cost: fields.get("max_cost"),
            max_input_tokens: Number(fields.get("max_input_tokens")),
            max_output_tokens: Number(fields.get("max_output_tokens")),
            max_retries: Number(fields.get("max_retries")),
            timeout_seconds: Number(fields.get("timeout_seconds")),
            prompt_version: Number(fields.get("prompt_version")),
          });
        }}
      >
        <label>
          Primary route
          <input
            name="primary_model"
            defaultValue={task.primary_model}
            required
          />
        </label>
        <label>
          Fallback routes
          <input
            value={fallbacks}
            onChange={(event) => setFallbacks(event.target.value)}
            placeholder="gateway:model-name"
          />
        </label>
        <label>
          Allowed providers
          <input
            value={providersText}
            onChange={(event) => setProvidersText(event.target.value)}
            placeholder={providers.join(", ")}
            required
          />
        </label>
        <label>
          Max cost / call
          <input
            name="max_cost"
            type="number"
            min="0"
            step="0.000001"
            defaultValue={task.max_cost}
            required
          />
        </label>
        <label>
          Input tokens
          <input
            name="max_input_tokens"
            type="number"
            min="128"
            max="100000"
            defaultValue={task.max_input_tokens}
            required
          />
        </label>
        <label>
          Output tokens
          <input
            name="max_output_tokens"
            type="number"
            min="32"
            max="10000"
            defaultValue={task.max_output_tokens}
            required
          />
        </label>
        <label>
          Retries
          <input
            name="max_retries"
            type="number"
            min="0"
            max="5"
            defaultValue={task.max_retries}
            required
          />
        </label>
        <label>
          Timeout seconds
          <input
            name="timeout_seconds"
            type="number"
            min="0.1"
            max="120"
            step="0.1"
            defaultValue={task.timeout_seconds}
            required
          />
        </label>
        <label>
          Active prompt version
          <input
            name="prompt_version"
            type="number"
            min="1"
            defaultValue={task.prompt_version}
            required
          />
        </label>
        <button disabled={busy} type="submit">
          Save task settings
        </button>
      </form>
      <div className="ai-admin-prompt-section">
        <h4>Prompt versions</h4>
        <div className="ai-admin-prompts">
          {task.prompts.map((prompt) => (
            <article key={prompt.id}>
              <div>
                <strong>v{prompt.version}</strong>
                <span>{prompt.status}</span>
                <small>
                  {prompt.scope === "system"
                    ? "system default"
                    : "portal prompt"}
                </small>
              </div>
              <pre>{prompt.template}</pre>
              {prompt.scope === "portal" && prompt.status !== "active" ? (
                <button
                  disabled={busy}
                  type="button"
                  onClick={() => void activatePrompt(prompt.id)}
                >
                  Activate
                </button>
              ) : null}
            </article>
          ))}
          {!task.prompts.length ? (
            <p className="ai-admin-empty">No prompt versions.</p>
          ) : null}
        </div>
        <details>
          <summary>Create a draft prompt</summary>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void createPrompt(task.task, event.currentTarget);
            }}
          >
            <label>
              Prompt template
              <textarea
                name="template"
                minLength={20}
                maxLength={12000}
                rows={5}
                required
              />
            </label>
            <label>
              Release notes
              <input name="notes" maxLength={1000} />
            </label>
            <button disabled={busy} type="submit">
              Create draft
            </button>
          </form>
        </details>
      </div>
      <div className="ai-admin-experiment">
        <h4>A/B prompt test</h4>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const fields = new FormData(event.currentTarget);
            void save(`/admin/ai/experiments/${task.task}`, {
              name: fields.get("experiment_name"),
              prompt_version_a_id: promptA,
              prompt_version_b_id: promptB,
              variant_b_percent: Number(fields.get("variant_b_percent")),
              status: fields.get("status"),
            });
          }}
        >
          <label>
            Test name
            <input
              name="experiment_name"
              defaultValue={experiment?.name ?? `${task.task} prompt test`}
              required
            />
          </label>
          <label>
            Variant A
            <select
              value={promptA}
              onChange={(event) => setPromptA(event.target.value)}
              required
            >
              <option value="">Select active portal prompt</option>
              {activePrompts
                .filter((prompt) => prompt.scope === "portal")
                .map((prompt) => (
                  <option key={prompt.id} value={prompt.id}>
                    v{prompt.version}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Variant B
            <select
              value={promptB}
              onChange={(event) => setPromptB(event.target.value)}
              required
            >
              <option value="">Select active portal prompt</option>
              {activePrompts
                .filter((prompt) => prompt.scope === "portal")
                .map((prompt) => (
                  <option key={prompt.id} value={prompt.id}>
                    v{prompt.version}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Variant B traffic %
            <input
              name="variant_b_percent"
              type="number"
              min="1"
              max="99"
              defaultValue={experiment?.variant_b_percent ?? 50}
              required
            />
          </label>
          <label>
            Status
            <select name="status" defaultValue={experiment?.status ?? "paused"}>
              <option value="paused">Paused</option>
              <option value="running">Running</option>
            </select>
          </label>
          <button
            disabled={
              busy ||
              activePrompts.filter((prompt) => prompt.scope === "portal")
                .length < 2
            }
            type="submit"
          >
            Save experiment
          </button>
        </form>
        <small>
          Assignments stay stable per portal, task and canonical content ID.
        </small>
      </div>
    </article>
  );
}
