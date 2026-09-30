"use client";

import { useState } from "react";

export function ResilientMedia({
  source,
  fallbackSymbol = "★",
}: {
  source?: string | null;
  fallbackSymbol?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!source || failed) {
    return (
      <div className="media-frame media-fallback" aria-hidden="true">
        <span>{fallbackSymbol}</span>
      </div>
    );
  }
  return (
    <div className="media-frame media-image" aria-hidden="true">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={source} alt="" onError={() => setFailed(true)} />
    </div>
  );
}
