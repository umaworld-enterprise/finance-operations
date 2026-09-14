"use client";

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, ApiHttpError } from "@/lib/api";
import { getToken, setToken, clearToken } from "@/lib/auth-token";
import { loadGoogleIdentity } from "@/lib/google-identity";
import type { AppUser } from "@/types";

const DEV_USER: AppUser = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "admin@sunshine.dev",
  full_name: "Dev Admin",
  role: "super_admin",
  is_active: true,
  last_login_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
  onboarding_completed: true,
  secondary_email: null,
  department: null,
};

const isDev = process.env.NODE_ENV === "development";

interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AppUser;
}

interface AuthState {
  user: AppUser | null;
  loading: boolean;
  authError: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(isDev ? DEV_USER : null);
  const [loading, setLoading] = useState(!isDev);
  const [authError, setAuthError] = useState<string | null>(null);
  const fetchedRef = useRef(false);
  const router = useRouter();

  const fetchAppUser = useCallback(async () => {
    if (isDev) {
      setUser(DEV_USER);
      setLoading(false);
      return;
    }

    if (fetchedRef.current) return;
    fetchedRef.current = true;

    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const { data } = await api.get<AppUser>("/auth/me");
      setUser(data);
      setAuthError(null);
    } catch (err: unknown) {
      setUser(null);
      if (err instanceof ApiHttpError) {
        if (err.status === 403) {
          setAuthError(/deactiv/i.test(err.message) ? "deactivated" : "not_registered");
        } else if (err.status === 401) {
          // Expired token — clear it so the user sees the sign-in button cleanly.
          clearToken();
          setAuthError(null);
        } else {
          // Backend returned an unexpected HTTP error (e.g. 500) — don't claim the user is unregistered.
          setAuthError("service_unavailable");
        }
      } else {
        // Network timeout or offline — distinguish from "not registered".
        setAuthError("service_unavailable");
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (isDev) return;
    fetchAppUser();
  }, [fetchAppUser]);

  const handleAuthCode = useCallback(
    async (code: string) => {
      try {
        const { data } = await api.post<LoginResponse>("/auth/google/login", { code });
        setToken(data.access_token, data.expires_in);
        fetchedRef.current = true;
        setUser(data.user);
        setAuthError(null);
        router.push("/"); // RootPage routes to the user's role home
      } catch (err: unknown) {
        setUser(null);
        if (err instanceof ApiHttpError && err.status === 403) {
          setAuthError(/deactiv/i.test(err.message) ? "deactivated" : "not_registered");
          router.push("/"); // RootPage renders the matching error screen
        } else {
          // Google exchange failed / backend unreachable — stay on the login
          // page and let it show the failure banner.
          setAuthError("auth_failed");
        }
      } finally {
        setLoading(false);
      }
    },
    [router]
  );

  const signInWithGoogle = useCallback(async () => {
    setAuthError(null);
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) {
      console.error("[auth] NEXT_PUBLIC_GOOGLE_CLIENT_ID is not set");
      setAuthError("auth_failed");
      return;
    }

    try {
      setLoading(true);
      await loadGoogleIdentity();
      const codeClient = window.google!.accounts!.oauth2!.initCodeClient({
        client_id: clientId,
        scope: "openid email profile",
        ux_mode: "popup",
        callback: (response) => {
          if (response.code) {
            void handleAuthCode(response.code);
          } else {
            setLoading(false);
            if (response.error) setAuthError("auth_failed");
          }
        },
        // Popup closed or blocked — just stop the spinner, no error banner.
        error_callback: () => setLoading(false),
      });
      codeClient.requestCode();
    } catch (err) {
      console.error("[auth] Google sign-in failed to start:", err);
      setLoading(false);
      setAuthError("auth_failed");
    }
  }, [handleAuthCode]);

  const signOut = useCallback(async () => {
    if (!isDev) {
      clearToken();
    }
    setUser(null);
    setAuthError(null);
    fetchedRef.current = false;
    window.location.href = "/login";
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, authError, signInWithGoogle, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
