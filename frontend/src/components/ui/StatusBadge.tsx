import { cn } from "@/lib/utils";
import {
  Clock,
  Pause,
  Check,
  X,
  RotateCcw,
  Hourglass,
  type LucideIcon,
} from "lucide-react";
import type { RequestStatus } from "@/types";

const STATUS_LABELS: Record<RequestStatus, string> = {
  pending_payment: "Pending Payment",
  hold_by_merchandiser: "On Hold",
  hold_by_accounts: "On Hold",
  payment_processed: "Processed",
  cancelled_by_merchandiser: "Cancelled",
  cancelled_by_accounts: "Cancelled",
  reopened: "Reopened",
  pending_hom_approval: "Awaiting HoM",
  rejected_by_hom: "Rejected",
};

const FULL_LABELS: Partial<Record<RequestStatus, string>> = {
  hold_by_merchandiser: "On Hold (by you)",
  hold_by_accounts: "On Hold (by Accounts)",
  cancelled_by_merchandiser: "Cancelled (by you)",
  cancelled_by_accounts: "Cancelled (by Accounts)",
  pending_hom_approval: "Waiting for HOM Approval",
  rejected_by_hom: "Rejected by HOD (Merchandiser)",
};

type Treatment = "filled" | "outlined" | "dashed" | "strikethrough" | "subtle";

const STATUS_TREATMENT: Record<RequestStatus, Treatment> = {
  pending_payment: "outlined",
  hold_by_merchandiser: "dashed",
  hold_by_accounts: "dashed",
  payment_processed: "filled",
  cancelled_by_merchandiser: "strikethrough",
  cancelled_by_accounts: "strikethrough",
  reopened: "subtle",
  pending_hom_approval: "dashed",
  rejected_by_hom: "strikethrough",
};

const STATUS_ICONS: Record<RequestStatus, LucideIcon> = {
  pending_payment: Clock,
  hold_by_merchandiser: Pause,
  hold_by_accounts: Pause,
  payment_processed: Check,
  cancelled_by_merchandiser: X,
  cancelled_by_accounts: X,
  reopened: RotateCcw,
  pending_hom_approval: Hourglass,
  rejected_by_hom: X,
};

interface StatusBadgeProps {
  status: RequestStatus;
  showFull?: boolean;
  className?: string;
}

export function StatusBadge({ status, showFull = false, className }: StatusBadgeProps) {
  const label = showFull && FULL_LABELS[status] ? FULL_LABELS[status] : STATUS_LABELS[status];
  const Icon = STATUS_ICONS[status];
  const treatment = STATUS_TREATMENT[status];

  const base =
    "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap";

  const treatmentClass: Record<Treatment, string> = {
    filled: "bg-primary text-primary-foreground border border-primary",
    outlined: "bg-background text-foreground border border-border",
    dashed: "bg-background text-foreground border border-dashed border-foreground/40",
    strikethrough: "bg-transparent text-muted-foreground border border-transparent line-through",
    subtle: "bg-secondary text-secondary-foreground border border-border",
  };

  return (
    <span className={cn(base, treatmentClass[treatment], className)}>
      <Icon className="h-3 w-3 shrink-0" />
      {label}
    </span>
  );
}
