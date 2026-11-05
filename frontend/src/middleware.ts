import { type NextRequest, NextResponse } from "next/server";

const AUTH_COOKIE_NAME = "fo_token";

// A browser clock running slightly ahead of the server made freshly issued
// tokens look already expired here, bouncing the user straight back to
// /login after a successful sign-in (5 Nov 2026).
const CLOCK_SKEW_MS = 2 * 60 * 1000;

/** Cheap local check: is there a plausible session?
 *
 *  No signature verification — the backend authorises every API call and is
 *  the only authority. This gate therefore errs towards LETTING THROUGH: a
 *  cookie that is present but unreadable means the API will answer 401 and
 *  the app will clear it, which is far better than a login loop caused by a
 *  parsing quirk. Only an absent cookie, or one demonstrably expired beyond
 *  the skew allowance, is turned away. */
function hasLiveSession(request: NextRequest): boolean {
  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;
  if (!token) return false;
  try {
    const raw = token.split(".")[1];
    if (!raw) return true;                       // not a JWT we can read — let the API judge
    // base64url → base64, restoring the padding atob needs.
    const b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, "=")));
    if (typeof payload.exp !== "number") return true;
    return payload.exp * 1000 + CLOCK_SKEW_MS > Date.now();
  } catch {
    return true;                                  // unreadable ≠ unauthenticated
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
