"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getPushState, subscribeToPush } from "@/lib/push";

const PROMPT_DISMISS_KEY = "adt-push-prompt-dismissed";
const TOAST_SESSION_KEY = "adt-push-toast-shown";

/**
 * Global push-notification opt-in, mounted in the dashboard layout so it
 * greets every role right after login/onboarding:
 *  - first eligible visit → a centered pop-up asking to enable push
 *  - dismissed before    → a small once-per-session reminder toast
 * Shows nothing when push is unsupported (e.g. iOS Safari tab), blocked at
 * the browser level, or already subscribed.
 */
export function PushPrompt() {
  const [showModal, setShowModal] = useState(false);
  const [enabling, setEnabling] = useState(false);

  const enable = async () => {
    setEnabling(true);
    try {
      await subscribeToPush();
      window.localStorage.setItem(PROMPT_DISMISS_KEY, "1");
      setShowModal(false);
      toast.success("Push notifications enabled.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Could not enable notifications.");
    } finally {
      setEnabling(false);
    }
  };

  const dismiss = () => {
    window.localStorage.setItem(PROMPT_DISMISS_KEY, "1");
    setShowModal(false);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const state = await getPushState();
      if (cancelled || state !== "unsubscribed") return;
      if (!window.localStorage.getItem(PROMPT_DISMISS_KEY)) {
        setShowModal(true);
      } else if (!window.sessionStorage.getItem(TOAST_SESSION_KEY)) {
        window.sessionStorage.setItem(TOAST_SESSION_KEY, "1");
        toast("Please enable the notifications", {
          description: "Turn on push to get payment updates on this device.",
          action: { label: "Enable", onClick: () => void enable() },
          duration: 8000,
        });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!showModal) return null;

  return (
    <div
      className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="push-prompt-title"
    >
      <div className="w-full max-w-sm rounded-xl border border-border bg-background p-6 shadow-xl">
        <div className="flex items-center justify-center h-12 w-12 rounded-full bg-secondary mx-auto">
          <BellRing className="h-6 w-6 text-primary" />
        </div>
        <h2 id="push-prompt-title" className="mt-4 text-base font-semibold text-foreground text-center">
          Please enable push notifications
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground text-center">
          Get notified the moment a payment is processed — including the TT copy
          link — even when the app is closed.
        </p>
        <div className="mt-5 flex flex-col-reverse sm:flex-row gap-2 sm:justify-center">
          <Button variant="outline" onClick={dismiss} disabled={enabling}>
            Not now
          </Button>
          <Button onClick={enable} disabled={enabling}>
            {enabling ? "Enabling…" : "Enable notifications"}
          </Button>
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground text-center">
          You can change this anytime in Settings.
        </p>
      </div>
    </div>
  );
}
