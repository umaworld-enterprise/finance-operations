import { AlertTriangle } from "lucide-react";
import { formatCurrency } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { SupplierDefaultStatus } from "@/types";

interface Props {
  status: SupplierDefaultStatus;
  onContinue?: () => void;
  onWithdraw?: () => void;
}

export function SupplierDefaultAlert({ status, onContinue, onWithdraw }: Props) {
  if (!status.is_defaulted) return null;

  const hasSoftOverride = onContinue !== undefined && onWithdraw !== undefined;

  return (
    <div className="rounded-lg bg-muted border border-foreground/20 p-4 space-y-3">
      <div className="flex items-center gap-2 text-foreground font-semibold">
        <AlertTriangle className="h-5 w-5 shrink-0" />
        This supplier is on the Defaulted Supplier List
      </div>
      <p className="text-sm text-foreground">
        <span className="font-medium">Outstanding amount:</span>{" "}
        {formatCurrency(status.outstanding_amount ?? 0, status.currency ?? "USD")}
      </p>
      <p className="text-sm text-foreground">
        <span className="font-medium">Reason:</span> {status.default_reason}
      </p>

      {hasSoftOverride ? (
        <>
          <p className="text-sm text-muted-foreground">
            You may still submit this request, but it will require approval from the Head of Merchandising before proceeding to Accounts.
          </p>
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={onWithdraw}>
              Withdraw
            </Button>
            <Button type="button" variant="default" size="sm" onClick={onContinue}>
              Still Continue
            </Button>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground font-medium">
          This request cannot be submitted. Escalate to the Finance Team to resolve the flag.
        </p>
      )}
    </div>
  );
}
