import { type NextRequest, NextResponse } from "next/server";

const AUTH_COOKIE_NAME = "fo_token";

/** Cheap local check: token present and its `exp` claim not in the past.
 *  No signature verification here — that happens in the backend on every API
 *  call. The middleware only needs an "is there a plausible session" gate. */
function hasLiveSession(request: NextRequest): boolean {
  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;
  if (!token) return false;
  try {
    const payloadB64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(payloadB64));
    return typeof payload.exp === "number" && payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public routes — let through without checking session
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/form") ||
    pathname.startsWith("/onboarding") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon.ico") ||
    pathname === "/sw.js" ||
    // Static assets fetched by the browser without auth cookies — redirecting
    // these to /login returns HTML where JSON/images are expected.
    pathname === "/manifest.webmanifest" ||
    /\.(png|jpg|jpeg|svg|ico|webp|gif)$/.test(pathname)
  ) {
    return NextResponse.next();
  }

  // Dev bypass — skip auth check in development
  if (process.env.NODE_ENV === "development") {
    return NextResponse.next();
  }

  if (!hasLiveSession(request)) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sw.js|manifest.webmanifest|login|form|onboarding|.*\\.(?:png|jpg|jpeg|svg|ico|webp|gif)$).*)",
  ],
};
