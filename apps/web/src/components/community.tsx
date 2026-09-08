"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import type { Entity } from "@/lib/public-api";

type User = {
  id: string;
  email: string;
  role: string;
  display_name: string;
  bio: string | null;
  preferred_language: string;
  timezone: string | null;
};
type Comment = {
  id: string;
  user_id: string;
  parent_id: string | null;
  author_name: string;
  body: string;
  status: string;
  score: number;
  created_at: string;
};

const root = "/api/v1/portals/texas";

function cookie(name: string) {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const csrf = cookie("news_csrf");
  if (csrf && init?.method && !["GET", "HEAD"].includes(init.method)) {
    headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(`${root}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

function Account({ user, onAuth }: { user: User | null; onAuth: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body: Record<string, string> = {
      email: String(data.get("email")),
      password: String(data.get("password")),
    };
    if (mode === "register")
      body.display_name = String(data.get("display_name"));
    try {
      await api(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMessage("");
      onAuth();
    } catch {
      setMessage(mode === "login" ? "Sign-in failed." : "Registration failed.");
    }
  }

  if (user) {
    return (
      <form
        className="community-account profile-form"
        onSubmit={async (event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          await api("/auth/profile", {
            method: "PUT",
            body: JSON.stringify({
              display_name: data.get("display_name"),
              bio: data.get("bio") || null,
              avatar_url: null,
              preferred_language: user.preferred_language,
              timezone: user.timezone,
            }),
          });
          onAuth();
        }}
      >
        <span>Signed in as {user.display_name}</span>
        <input
          aria-label="Display name"
          name="display_name"
          defaultValue={user.display_name}
          maxLength={80}
          required
        />
        <input
          aria-label="Profile bio"
          name="bio"
          defaultValue={user.bio ?? ""}
          maxLength={500}
          placeholder="Short bio"
        />
        <button type="submit">Update profile</button>
        <button
          type="button"
          onClick={async () => {
            await api("/auth/logout", { method: "POST" });
            onAuth();
          }}
        >
          Log out
        </button>
      </form>
    );
  }
  return (
    <form className="auth-form" onSubmit={submit}>
      <h3>
        {mode === "login" ? "Join the conversation" : "Create your profile"}
      </h3>
      {mode === "register" ? (
        <input name="display_name" placeholder="Display name" required />
      ) : null}
      <input name="email" type="email" placeholder="Email" required />
      <input
        name="password"
        type="password"
        minLength={12}
        placeholder="Password (12+ characters)"
        required
      />
      <button type="submit">{mode === "login" ? "Log in" : "Register"}</button>
      <button
        type="button"
        className="text-button"
        onClick={() => setMode(mode === "login" ? "register" : "login")}
      >
        {mode === "login" ? "Create an account" : "Use an existing account"}
      </button>
      {message ? <p role="alert">{message}</p> : null}
    </form>
  );
}

export function CommunityPanel({
  storySlug,
  entities,
}: {
  storySlug: string;
  entities: Entity[];
}) {
  const [user, setUser] = useState<User | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    const page = await api<{ items: Comment[] }>(
      `/community/stories/${encodeURIComponent(storySlug)}/comments`,
    );
    setComments(page.items);
    try {
      setUser(await api<User>("/auth/me"));
    } catch {
      setUser(null);
    }
  }, [storySlug]);

  useEffect(() => {
    const pending = window.setTimeout(() => {
      void refresh().catch(() =>
        setNotice("Comments are temporarily unavailable."),
      );
    }, 0);
    return () => window.clearTimeout(pending);
  }, [refresh]);

  async function postComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await api(`/community/stories/${encodeURIComponent(storySlug)}/comments`, {
      method: "POST",
      body: JSON.stringify({ id: crypto.randomUUID(), body: data.get("body") }),
    });
    form.reset();
    await refresh();
  }

  async function action(path: string, method = "PUT", body?: object) {
    if (!user) return setNotice("Log in to use community features.");
    await api(path, { method, body: body ? JSON.stringify(body) : undefined });
    setNotice("Saved.");
    await refresh();
  }

  async function reply(comment: Comment) {
    if (!user) return setNotice("Log in to reply.");
    const body = window.prompt(`Reply to ${comment.author_name}`)?.trim();
    if (!body) return;
    await api(`/community/stories/${encodeURIComponent(storySlug)}/comments`, {
      method: "POST",
      body: JSON.stringify({
        id: crypto.randomUUID(),
        body,
        parent_id: comment.id,
      }),
    });
    await refresh();
  }

  return (
    <section className="community-panel" aria-labelledby="community-title">
      <div className="community-heading">
        <div>
          <span className="page-kicker">Community</span>
          <h2 id="community-title">Texas talks</h2>
        </div>
        <div className="community-actions">
          <button
            type="button"
            onClick={() =>
              void action(
                `/community/stories/${encodeURIComponent(storySlug)}/reactions`,
                "PUT",
                { reaction_type: "like" },
              )
            }
          >
            Like
          </button>
          <button
            type="button"
            onClick={() =>
              void action(
                `/community/stories/${encodeURIComponent(storySlug)}/reactions`,
                "PUT",
                { reaction_type: "love" },
              )
            }
          >
            Love
          </button>
          <button
            type="button"
            onClick={() =>
              void action(
                `/community/stories/${encodeURIComponent(storySlug)}/save`,
              )
            }
          >
            Save
          </button>
          {entities[0] ? (
            <button
              type="button"
              onClick={() =>
                void action(`/community/follows/entity/${entities[0].id}`)
              }
            >
              Follow {entities[0].name}
            </button>
          ) : null}
        </div>
      </div>
      <Account user={user} onAuth={() => void refresh()} />
      {user ? (
        <form
          className="comment-form"
          onSubmit={(event) => void postComment(event)}
        >
          <label htmlFor="comment-body">Add a comment</label>
          <textarea id="comment-body" name="body" maxLength={4000} required />
          <button type="submit">Post comment</button>
        </form>
      ) : null}
      {notice ? (
        <p className="community-notice" role="status">
          {notice}
        </p>
      ) : null}
      <ol className="comment-list">
        {comments.map((comment) => (
          <li
            key={comment.id}
            className={comment.parent_id ? "reply" : undefined}
          >
            <strong>{comment.author_name}</strong>
            <time dateTime={comment.created_at}>
              {new Date(comment.created_at).toLocaleString()}
            </time>
            <p>{comment.body}</p>
            <div>
              <button type="button" onClick={() => void reply(comment)}>
                Reply
              </button>
              <button
                type="button"
                onClick={() =>
                  void action(
                    `/community/stories/${encodeURIComponent(storySlug)}/comments/${comment.id}/reactions`,
                    "PUT",
                    { reaction_type: "like" },
                  )
                }
              >
                Like {comment.score || ""}
              </button>
              <button
                type="button"
                onClick={() =>
                  void action(
                    `/community/comments/${comment.id}/reports`,
                    "POST",
                    { reason: "other" },
                  )
                }
              >
                Report
              </button>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
