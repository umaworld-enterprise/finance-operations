"use client";

// Presence + "while you were away" (23 Sep 2026, executive request).
//
// A heartbeat runs only while the tab is VISIBLE, so the gap it leaves behind
// is exactly the time the user was away. On return we ask the server what
// arrived during that gap and pop the dialog when it says so (a real absence
// — 30+ minutes — with new requests waiting).

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import notificationService, { type AwaySummary } from "@/services/notificationService";
import { useAuth } from "@/hooks/useAuth";

const HEARTBEAT_MS = 60_000;

export function usePresence(enabled: boolean) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [summary, setSummary] = useState<AwaySummary | null>(null);
  // Guards against two checks racing when a tab is toggled quickly.
  const checking = useRef(false);

  useEffect(() => {
    if (!enabled || !user) return;

    let timer: ReturnType<typeof setInterval> | null = null;

    const beat = () => {
      void notificationService.heartbeat().catch(() => {});
    };

    const startBeating = () => {
      if (timer === null) timer = setInterval(beat, HEARTBEAT_MS);
    };

    const stopBeating = () => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };

    // On return: read the away summary BEFORE the next heartbeat overwrites
    // the timestamp it is measured against.
    const checkOnReturn = async () => {
      if (checking.current) return;
      checking.current = true;
      try {
        const result = await notificationService.awaySummary();
        if (result.show) {
          setSummary(result);
          // The queue itself may be well out of date after a long absence.
          qc.invalidateQueries({ queryKey: ["requests"] });
        }
      } catch {
        // A failed summary must never block the app.
      } finally {
        checking.current = false;
        beat();
      }
    };

    const onVisibility = () => {
      if (document.hidden) {
        stopBeating();
      } else {
        void checkOnReturn();
        startBeating();
      }
    };

    // First mount counts as a return — it covers a fresh login or reload.
    void checkOnReturn();
    startBeating();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stopBeating();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, user, qc]);

  return { summary, dismiss: () => setSummary(null) };
}
