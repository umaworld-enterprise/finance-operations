"use client";

// "While you were away" pop-up (23 Sep 2026, executive request): tells the
// Accounts team how many requests reached their queue during an absence, and
// takes them straight to it.

import { Inbox } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { AwaySummary } from "@/services/notificationService";

/** "2 hours" / "45 minutes" — the absence in words. */
function humanGap(minutes: number): string {
  if (minutes < 60) return `${minutes} minutes`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "an hour" : `${hours} hours`;
  const days = Math.round(hours / 24);
  return days === 1 ? "a day" : `${days} days`;
}

export function AwayDialog({
  summary,
  onClose,
  onGoToQueue,
}: {
  summary: AwaySummary | null;
  onClose: () => void;
  onGoToQueue: () => void;
}) {
  if (!summary) return null;
  const { new_requests: count, away_minutes: minutes } = summary;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <div className="flex items-start gap-3">
            <div className="bg-muted rounded-full p-2 shrink-0">
              <Inbox className="h-5 w-5 text-foreground" />
            </div>
            <div className="flex-1">
              <DialogTitle>
                {count} new {count === 1 ? "request" : "requests"} while you were away
              </DialogTitle>
              <DialogDescription>
                {count === 1 ? "A request" : `${count} requests`} reached the payment queue
                over the last {humanGap(minutes)} and {count === 1 ? "is" : "are"} waiting
                for the Accounts team. Modified files are marked with a red dot in the list.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>
            Dismiss
          </Button>
          <Button size="sm" onClick={onGoToQueue}>
            View payment queue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
