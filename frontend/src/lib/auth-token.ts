// App-issued JWT storage.
//
// The token lives in a plain (JS-readable) cookie rather than localStorage so
// the Next.js middleware can gate page navigations server-side with the same
// value the API client sends. Fine-grained authorization always happens in
// the backend on every request — the cookie is only a session pointer.

const COOKIE_NAME = "fo_token";

export function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${COOKIE_NAME}=`));
  return match ? decodeURIComponent(match.slice(COOKIE_NAME.length + 1)) : null;
}

export function setToken(token: string, expiresInSeconds: number): void {
  if (typeof document === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie =
    `${COOKIE_NAME}=${encodeURIComponent(token)}` +
    `; Path=/; Max-Age=${expiresInSeconds}; SameSite=Lax${secure}`;
}

export function clearToken(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export const AUTH_COOKIE_NAME = COOKIE_NAME;
