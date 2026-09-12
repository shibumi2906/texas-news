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

function cookie(name: string) {
  return document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

async function api<T>(
  portalSlug: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const csrf = cookie("news_csrf");
  if (csrf && init?.method && !["GET", "HEAD"].includes(init.method)) {
    headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(
    `/api/v1/portals/${encodeURIComponent(portalSlug)}${path}`,
    {
      ...init,
      headers,
      credentials: "same-origin",
    },
  );
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

function Account({
  user,
  portalSlug,
  language,
  onAuth,
}: {
  user: User | null;
  portalSlug: string;
  language: string;
  onAuth: () => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");
  const es = language === "es";

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
      await api(portalSlug, `/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMessage("");
      onAuth();
    } catch {
      setMessage(
        mode === "login"
          ? es
            ? "No se pudo iniciar sesión."
            : "Sign-in failed."
          : es
            ? "No se pudo completar el registro."
            : "Registration failed.",
      );
    }
  }

  if (user) {
    return (
      <form
        className="community-account profile-form"
        onSubmit={async (event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          await api(portalSlug, "/auth/profile", {
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
        <span>
          {es ? "Sesión iniciada como" : "Signed in as"} {user.display_name}
        </span>
        <input
          aria-label={es ? "Nombre visible" : "Display name"}
          name="display_name"
          defaultValue={user.display_name}
          maxLength={80}
          required
        />
        <input
          aria-label={es ? "Biografía del perfil" : "Profile bio"}
          name="bio"
          defaultValue={user.bio ?? ""}
          maxLength={500}
          placeholder={es ? "Biografía breve" : "Short bio"}
        />
        <button type="submit">
          {es ? "Actualizar perfil" : "Update profile"}
        </button>
        <button
          type="button"
          onClick={async () => {
            await api(portalSlug, "/auth/logout", { method: "POST" });
            onAuth();
          }}
        >
          {es ? "Cerrar sesión" : "Log out"}
        </button>
      </form>
    );
  }
  return (
    <form className="auth-form" onSubmit={submit}>
      <h3>
        {mode === "login"
          ? es
            ? "Únete a la conversación"
            : "Join the conversation"
          : es
            ? "Crea tu perfil"
            : "Create your profile"}
      </h3>
      {mode === "register" ? (
        <input
          name="display_name"
          placeholder={es ? "Nombre visible" : "Display name"}
          required
        />
      ) : null}
      <input
        name="email"
        type="email"
        placeholder={es ? "Correo electrónico" : "Email"}
        required
      />
      <input
        name="password"
        type="password"
        minLength={12}
        placeholder={
          es ? "Contraseña (12+ caracteres)" : "Password (12+ characters)"
        }
        required
      />
      <button type="submit">
        {mode === "login"
          ? es
            ? "Iniciar sesión"
            : "Log in"
          : es
            ? "Registrarse"
            : "Register"}
      </button>
      <button
        type="button"
        className="text-button"
        onClick={() => setMode(mode === "login" ? "register" : "login")}
      >
        {mode === "login"
          ? es
            ? "Crear una cuenta"
            : "Create an account"
          : es
            ? "Usar una cuenta existente"
            : "Use an existing account"}
      </button>
      {message ? <p role="alert">{message}</p> : null}
    </form>
  );
}

export function CommunityPanel({
  portalSlug = "texas",
  language = "en",
  storySlug,
  entities,
}: {
  portalSlug?: string;
  language?: string;
  storySlug: string;
  entities: Entity[];
}) {
  const [user, setUser] = useState<User | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [notice, setNotice] = useState("");
  const es = language === "es";

  const refresh = useCallback(async () => {
    const page = await api<{ items: Comment[] }>(
      portalSlug,
      `/community/stories/${encodeURIComponent(storySlug)}/comments`,
    );
    setComments(page.items);
    try {
      setUser(await api<User>(portalSlug, "/auth/me"));
    } catch {
      setUser(null);
    }
  }, [portalSlug, storySlug]);

  useEffect(() => {
    const pending = window.setTimeout(() => {
      void refresh().catch(() =>
        setNotice(
          es
            ? "Los comentarios no están disponibles temporalmente."
            : "Comments are temporarily unavailable.",
        ),
      );
    }, 0);
    return () => window.clearTimeout(pending);
  }, [es, refresh]);

  async function postComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await api(
      portalSlug,
      `/community/stories/${encodeURIComponent(storySlug)}/comments`,
      {
        method: "POST",
        body: JSON.stringify({
          id: crypto.randomUUID(),
          body: data.get("body"),
        }),
      },
    );
    form.reset();
    await refresh();
  }

  async function action(path: string, method = "PUT", body?: object) {
    if (!user)
      return setNotice(
        es
          ? "Inicia sesión para usar las funciones de la comunidad."
          : "Log in to use community features.",
      );
    await api(portalSlug, path, {
      method,
      body: body ? JSON.stringify(body) : undefined,
    });
    setNotice(es ? "Guardado." : "Saved.");
    await refresh();
  }

  async function reply(comment: Comment) {
    if (!user)
      return setNotice(
        es ? "Inicia sesión para responder." : "Log in to reply.",
      );
    const body = window
      .prompt(`${es ? "Responder a" : "Reply to"} ${comment.author_name}`)
      ?.trim();
    if (!body) return;
    await api(
      portalSlug,
      `/community/stories/${encodeURIComponent(storySlug)}/comments`,
      {
        method: "POST",
        body: JSON.stringify({
          id: crypto.randomUUID(),
          body,
          parent_id: comment.id,
        }),
      },
    );
    await refresh();
  }

  return (
    <section className="community-panel" aria-labelledby="community-title">
      <div className="community-heading">
        <div>
          <span className="page-kicker">{es ? "Comunidad" : "Community"}</span>
          <h2 id="community-title">{es ? "Texas conversa" : "Texas talks"}</h2>
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
            {es ? "Me gusta" : "Like"}
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
            {es ? "Me encanta" : "Love"}
          </button>
          <button
            type="button"
            onClick={() =>
              void action(
                `/community/stories/${encodeURIComponent(storySlug)}/save`,
              )
            }
          >
            {es ? "Guardar" : "Save"}
          </button>
          {entities[0] ? (
            <button
              type="button"
              onClick={() =>
                void action(`/community/follows/entity/${entities[0].id}`)
              }
            >
              {es ? "Seguir a" : "Follow"} {entities[0].name}
            </button>
          ) : null}
        </div>
      </div>
      <Account
        user={user}
        portalSlug={portalSlug}
        language={language}
        onAuth={() => void refresh()}
      />
      {user ? (
        <form
          className="comment-form"
          onSubmit={(event) => void postComment(event)}
        >
          <label htmlFor="comment-body">
            {es ? "Añadir un comentario" : "Add a comment"}
          </label>
          <textarea id="comment-body" name="body" maxLength={4000} required />
          <button type="submit">
            {es ? "Publicar comentario" : "Post comment"}
          </button>
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
                {es ? "Responder" : "Reply"}
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
                {es ? "Me gusta" : "Like"} {comment.score || ""}
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
                {es ? "Denunciar" : "Report"}
              </button>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
