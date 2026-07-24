import { type NextRequest, NextResponse } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public routes — let through without checking session
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/auth") ||
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

  const response = NextResponse.next({ request });

  try {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
            cookiesToSet.forEach(({ name, value, options }) => {
              request.cookies.set(name, value);
              response.cookies.set(name, value, options);
            });
          },
        },
      }
    );

    // getSession() parses the JWT from cookies locally — no network call.
    // getUser() would round-trip to Supabase on EVERY navigation (100-400ms).
    // Fine-grained authorization happens in the backend on each API call,
    // so the middleware only needs a cheap "is there a session" gate.
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session) {
      const loginUrl = new URL("/login", request.url);
      return NextResponse.redirect(loginUrl);
    }
  } catch {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sw.js|manifest.webmanifest|login|auth|form|onboarding|.*\\.(?:png|jpg|jpeg|svg|ico|webp|gif)$).*)",
  ],
};
