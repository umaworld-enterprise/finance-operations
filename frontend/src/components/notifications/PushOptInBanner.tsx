"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRing, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isPushSupported, subscribeToPush } from "@/lib/push";

const DISMISS_KEY = "adt-push-banner-dismissed";

/**
 * One-time banner inviting the merchandiser to enable payment push
 * notifications. Shows only while permission is still undecided.
 */
export function PushOptInBanner() {
  const [visible, setVisible] = useState(false);
  const [enabling, setEnabling] = useState(false);

  useEffect(() => {
    if (!isPushSupported()) return;
    if (Notification.permission !== "default") return;
    if (window.localStorage.getItem(DISMISS_KEY)) return;
    setVisible(true);
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    window.localStorage.setItem(DISMISS_KEY, "1");
    setVisible(false);
  };

  const enable = async () => {
    setEnabling(true);
    try {
      await subscribeToPush();
      toast.success("Payment notifications enabled.");
      setVisible(false);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Could not enable notifications.");
    } finally {
      setEnabling(false);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-border bg-secondary p-4">
      <BellRing className="h-5 w-5 text-primary shrink-0 hidden sm:block" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">Get notified when payments are processed</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Enable push notifications to receive the payment confirmation and TT copy link instantly.
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button size="sm" onClick={enable} disabled={enabling}>
          {enabling ? "Enabling…" : "Enable"}
        </Button>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
