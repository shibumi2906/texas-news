"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

type Answer = {
  answer: string;
  status: "answered" | "insufficient_evidence";
  insufficient_evidence: boolean;
  generated: boolean;
  fallback_used: boolean;
  sources: { content_id: string; title: string; url: string }[];
  metadata: { timezone: string; ranking_authoritative: boolean };
};

function identity(storage: Storage, key: string): string {
  const existing = storage.getItem(key);
  if (existing) return existing;
  const value = crypto.randomUUID();
  storage.setItem(key, value);
  return value;
}

function requestBody(question?: string) {
  return {
    ...(question ? { question } : {}),
    language: "en",
    event_id: crypto.randomUUID(),
    anonymous_id: identity(localStorage, "ted-anonymous-id"),
    session_id: identity(sessionStorage, "ted-session-id"),
  };
}

export function AiAssistant({ storySlug }: { storySlug?: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error" | "limited">(
    "idle",
  );

  async function ask(endpoint: string, prompt?: string) {
    setState("loading");
    setAnswer(null);
    try {
      const response = await fetch(`/api/v1/portals/texas/${endpoint}`, {
        method: "POST",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody(prompt)),
      });
      if (response.status === 429) return setState("limited");
      if (!response.ok) throw new Error("AI answer unavailable");
      setAnswer((await response.json()) as Answer);
      setState("idle");
    } catch {
      setState("error");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = question.trim();
    if (prompt.length < 3) return;
    void ask(
      storySlug
        ? `stories/${encodeURIComponent(storySlug)}/ai-question`
        : "ai/search",
      prompt,
    );
  }

  return (
    <section
      className="ai-assistant"
      aria-labelledby={storySlug ? "ask-story-title" : "ask-ai-title"}
    >
      <span className="page-kicker">Ask AI</span>
      <h2 id={storySlug ? "ask-story-title" : "ask-ai-title"}>
        {storySlug ? "Ask about this story" : "Ask about Texas entertainment"}
      </h2>
      <p>
        Answers use only currently published stories on this platform and link
        the supporting coverage.
      </p>
      <form onSubmit={submit} className="ai-question-form">
        <label>
          Your question
          <input
            value={question}
            minLength={3}
            maxLength={500}
            required
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={
              storySlug
                ? "What are the key details?"
                : "What happened with the Mavericks?"
            }
          />
        </label>
        <button disabled={state === "loading"} type="submit">
          {state === "loading" ? "Checking coverage…" : "Ask"}
        </button>
      </form>
      {!storySlug ? (
        <div className="ai-quick-actions" aria-label="AI news briefs">
          <button
            disabled={state === "loading"}
            type="button"
            onClick={() => void ask("ai/trending")}
          >
            What&apos;s trending?
          </button>
          <button
            disabled={state === "loading"}
            type="button"
            onClick={() => void ask("ai/today")}
          >
            What happened today?
          </button>
        </div>
      ) : null}
      {state === "limited" ? (
        <p role="alert">Too many AI requests. Please try again shortly.</p>
      ) : null}
      {state === "error" ? (
        <p role="alert">AI answers are temporarily unavailable.</p>
      ) : null}
      {answer ? (
        <div className="ai-answer" aria-live="polite">
          <p>{answer.answer}</p>
          {answer.insufficient_evidence ? (
            <small>
              There was not enough published platform evidence to answer.
            </small>
          ) : (
            <>
              <h3>Supporting stories</h3>
              <ul>
                {answer.sources.map((source) => (
                  <li key={source.content_id}>
                    <Link href={source.url}>{source.title}</Link>
                  </li>
                ))}
              </ul>
              <small>
                {answer.generated ? "AI-generated" : "Grounded fallback"} from
                the linked stories.
                {answer.metadata.ranking_authoritative
                  ? " Ranking comes from the platform trending feed."
                  : ""}
              </small>
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}
