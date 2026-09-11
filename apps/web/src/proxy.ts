import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  const language =
    request.nextUrl.pathname === "/es" ||
    request.nextUrl.pathname.startsWith("/es/")
      ? "es"
      : "en";
  requestHeaders.set("x-site-language", language);
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
