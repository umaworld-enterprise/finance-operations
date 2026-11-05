import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { useProjectionReminders } from "@/hooks/useProjections";

/** Projection disclaimer on the request form (5 Nov 2026, executive request).
 *
 * From the 25th, a requester picking a vertical that still owes a projection
 * is reminded to file it. ADVISORY ONLY — it never blocks the request and
 * carries no override, because "there should be no blockers in creating
 * requests as it hampers work". It disappears for that vertical the moment
 * the projection is saved.
 */
export function ProjectionReminderAlert({ verticalId }: { verticalId?: string }) {
  const { data } = useProjectionReminders(!!verticalId);
  if (!verticalId || !data) return null;

  const owing = data.pending.some((p) => p.vertical_id === verticalId);
  if (!owing) return null;

  const name = data.pending.find((p) => p.vertical_id === verticalId)?.name;

  return (
    <div className="rounded-lg bg-muted border border-foreground/20 p-4 space-y-2">
      <div className="flex items-center gap-2 text-foreground font-semibold text-sm">
        <CalendarClock className="h-4 w-4 shrink-0" />
        Please update projection for the month {data.period_label} on or before{" "}
        {data.deadline_label}
      </div>
      <p className="text-sm text-muted-foreground">
        {name ?? "This vertical"} has no projection for {data.period_label} yet. Any
        merchandiser can file it — you do not have to be the one who raised this
        request.
      </p>
      <p className="text-sm text-muted-foreground">
        This is a reminder only. Your request is not blocked, and you can submit it now.{" "}
        <Link
          href="/projections"
          className="font-medium text-foreground underline underline-offset-2"
        >
          Open Projections
        </Link>
      </p>
    </div>
  );
}
