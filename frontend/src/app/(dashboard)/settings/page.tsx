"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Type, BellRing } from "lucide-react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { applyFontSize, getStoredFontSize, storeFontSize } from "@/lib/fontSize";
import {
  getPushState,
  isPushSupported,
  subscribeToPush,
  unsubscribeFromPush,
  type PushState,
} from "@/lib/push";
import type { FontSize } from "@/types";

const FONT_OPTIONS: { value: FontSize; label: string; description: string; sample: string }[] = [
  { value: "default", label: "Default", description: "Standard text size", sample: "text-sm" },
  { value: "large", label: "Large", description: "12.5% bigger everywhere", sample: "text-base" },
  { value: "xlarge", label: "Extra Large", description: "25% bigger everywhere", sample: "text-lg" },
];

export default function SettingsPage() {
  const [fontSize, setFontSize] = useState<FontSize>("default");
  const [pushState, setPushState] = useState<PushState>("unsupported");
  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => {
    setFontSize(getStoredFontSize());
    getPushState().then(setPushState).catch(() => setPushState("unsupported"));
  }, []);

  const changeFontSize = async (size: FontSize) => {
    const previous = fontSize;
    // Apply instantly — the PATCH persists it for other devices.
    setFontSize(size);
    storeFontSize(size);
    applyFontSize(size);
    try {
      await api.patch("/auth/preferences", { font_size: size });
    } catch (err: unknown) {
      setFontSize(previous);
      storeFontSize(previous);
      applyFontSize(previous);
      toast.error(err instanceof Error ? err.message : "Could not save the font size.");
    }
  };

  const togglePush = async (enable: boolean) => {
    setPushBusy(true);
    try {
      if (enable) {
        await subscribeToPush();
        setPushState("subscribed");
        toast.success("Push notifications enabled.");
      } else {
        await unsubscribeFromPush();
        setPushState("unsubscribed");
        toast.success("Push notifications disabled.");
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Could not update push notifications.");
      getPushState().then(setPushState).catch(() => undefined);
    } finally {
      setPushBusy(false);
    }
  };

  return (
    <RoleGuard
      allowedRoles={["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"]}
    >
      <TopNav title="Settings" subtitle="Personal preferences for this account" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-6 max-w-3xl mx-auto w-full">
        {/* Display */}
        <Card>
          <CardContent className="p-5 md:p-6 space-y-4">
            <div className="flex items-center gap-2">
              <Type className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold text-foreground">Display</h2>
            </div>
            <p className="text-xs text-muted-foreground -mt-2">
              Text size applies everywhere in the app, on this and all your devices.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {FONT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => changeFontSize(opt.value)}
                  aria-pressed={fontSize === opt.value}
                  className={cn(
                    "rounded-xl border p-4 text-left transition-all",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    fontSize === opt.value
                      ? "border-primary bg-secondary ring-1 ring-primary"
                      : "border-border hover:bg-muted/60"
                  )}
                >
                  <span className={cn("block font-semibold text-foreground", opt.sample)}>Aa</span>
                  <span className="block text-sm font-medium text-foreground mt-2">{opt.label}</span>
                  <span className="block text-xs text-muted-foreground mt-0.5">{opt.description}</span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Notifications */}
        <Card>
          <CardContent className="p-5 md:p-6 space-y-4">
            <div className="flex items-center gap-2">
              <BellRing className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold text-foreground">Notifications</h2>
            </div>
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">Push notifications</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Get an instant notification on this device when a payment is processed,
                  including the TT copy link.
                </p>
              </div>
              <Switch
                checked={pushState === "subscribed"}
                disabled={pushBusy || pushState === "unsupported" || pushState === "denied"}
                onCheckedChange={togglePush}
                aria-label="Toggle push notifications"
              />
            </div>
            {pushState === "denied" && (
              <p className="text-xs text-muted-foreground border border-border rounded-lg p-3 bg-muted/50">
                Notifications are blocked for this site in your browser settings. Allow them
                there, then come back and turn this on.
              </p>
            )}
            {!isPushSupported() && (
              <p className="text-xs text-muted-foreground border border-border rounded-lg p-3 bg-muted/50">
                Push isn&apos;t available in this browser. On iPhone/iPad, open this app in
                Safari, tap Share → &quot;Add to Home Screen&quot;, then enable notifications
                from the installed app (requires iOS 16.4 or later). The in-app bell at the
                top of the screen works everywhere.
              </p>
            )}
          </CardContent>
        </Card>
      </main>
    </RoleGuard>
  );
}
