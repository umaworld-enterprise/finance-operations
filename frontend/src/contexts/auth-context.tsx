"use client";

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { createClient } from "@/lib/supabase";
import { api, ApiHttpError } from "@/lib/api";
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
  const supabaseRef = useRef(createClient());
  const fetchedRef = useRef(false);

  const fetchAppUser = useCallback(async () => {
    if (isDev) {
      setUser(DEV_USER);
      setLoading(false);
      return;
    }

    if (fetchedRef.current) return;
    fetchedRef.current = true;

    const supabase = supabaseRef.current;
    try {
      // getSession() reads from localStorage — no blocking network call.
      // getUser() makes a Supabase network round-trip that can hang on stale PKCE/refresh state.
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.user) {
        setUser(null);
        setLoading(false);
        return;
      }

      const { data } = await api.get<AppUser>("/auth/me");
      setUser(data);
      setAuthError(null);
    } catch (err: unknown) {
      setUser(null);
      if (err instanceof ApiHttpError) {
        if (err.status === 403) {
          setAuthError(/deactiv/i.test(err.message) ? "deactivated" : "not_registered");
        } else if (err.status === 401) {
          // Expired token — clear session so the user sees the sign-in button cleanly.
          await supabaseRef.current.auth.signOut();
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

    const { data: { subscription } } = supabaseRef.current.auth.onAuthStateChange(
      async (event) => {
        if (event === "SIGNED_IN") {
          // If already fetched, this is a background token refresh — don't re-verify.
          if (fetchedRef.current) return;
          setLoading(true);
          await fetchAppUser();
        } else if (event === "SIGNED_OUT") {
          setUser(null);
          setAuthError(null);
          setLoading(false);
          fetchedRef.current = false;
        }
      }
    );

    return () => subscription.unsubscribe();
  }, [fetchAppUser]);

  const signInWithGoogle = useCallback(async () => {
    setAuthError(null);
    await supabaseRef.current.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  }, []);

  const signOut = useCallback(async () => {
    if (!isDev) {
      await supabaseRef.current.auth.signOut();
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
