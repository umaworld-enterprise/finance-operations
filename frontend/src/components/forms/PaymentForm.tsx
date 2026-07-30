"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useSavePayment, useProcessPayment, useSaveShipDate, REQUESTS_KEY } from "@/hooks/useRequests";
import notificationService from "@/services/notificationService";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { PaymentDetails } from "@/types";

const PAYMENT_STATUS_OPTIONS = [
  { value: "processed", label: "Processed" },
  { value: "rejected", label: "Rejected" },
  { value: "hold", label: "Hold" },
] as const;

// Payment Date, Bank, Payment Reference Number and Payment Status are
// mandatory (14 Jul 2026 change note, C7). Remarks stay optional.
const schema = z.object({
  payment_date: z.string().min(1, "Payment date is required"),
  bank: z.string().min(1, "Bank is required"),
  payment_reference_number: z.string().min(1, "Payment reference number is required"),
  // The select's placeholder submits "" — the enum rejects it with a clear
  // message, forcing an explicit pick.
  payment_status: z.enum(["processed", "rejected", "hold"], {
    errorMap: () => ({ message: "Payment status is required" }),
  }),
  accounts_remarks: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  requestId: string;
  isLocked: boolean;
  existing?: PaymentDetails | null;
  onProcessed?: () => void;
  // Finance Admin: may record the ship date only — everything else read-only.
  readOnly?: boolean;
  // Tranche-driven requests: processing and TT copies happen per tranche, so
  // the request-level Process button and TT upload are hidden. A legacy
  // request-level TT copy link (pre-tranche records) is still shown.
  trancheMode?: boolean;
}

export function PaymentForm({ requestId, isLocked, existing, onProcessed, readOnly = false, trancheMode = false }: Props) {
  const savePayment = useSavePayment();
  const processPayment = useProcessPayment();
  const saveShipDate = useSaveShipDate();
  const disabled = isLocked || readOnly;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  // Show the Drive link straight from the upload response — no refetch wait.
  const [uploadedPayment, setUploadedPayment] = useState<PaymentDetails | null>(null);

  const ttCopyUrl = uploadedPayment?.tt_copy_url ?? existing?.tt_copy_url ?? null;
  const ttCopyFilename = uploadedPayment?.tt_copy_filename ?? existing?.tt_copy_filename ?? null;

  const [shipDate, setShipDate] = useState("");
  useEffect(() => {
    setShipDate(existing?.ship_date ?? "");
  }, [existing?.ship_date]);

  const onSaveShipDate = async () => {
    if (!shipDate) return;
    try {
      await saveShipDate.mutateAsync({ requestId, shipDate });
      toast.success("Ship date saved — Cost of Fund has been frozen at this date.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save ship date.");
    }
  };

  const onUploadTtCopy = async () => {
    if (!selectedFile) return;
    if (selectedFile.size > 10 * 1024 * 1024) {
      toast.error("TT copy file must be 10 MB or smaller.");
      return;
    }
    setUploading(true);
    try {
      const payment = await notificationService.uploadTtCopy(requestId, selectedFile);
      setUploadedPayment(payment);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      queryClient.invalidateQueries({ queryKey: [...REQUESTS_KEY, requestId, "payment"] });
      toast.success("TT copy uploaded — link is ready and the merchandiser has been notified.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "TT copy upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    // values keeps the form in step with refetched data. Validation runs on
    // submit only (default mode), so legacy rows with NULL columns do not
    // trip errors on every render — they surface when Save is attempted.
    values: {
      payment_date: existing?.payment_date ?? "",
      bank: existing?.bank ?? "",
      payment_reference_number: existing?.payment_reference_number ?? "",
      payment_status: (existing?.payment_status ?? "") as FormValues["payment_status"],
      accounts_remarks: existing?.accounts_remarks ?? "",
    },
  });

  const onSave = async (data: FormValues) => {
    try {
      await savePayment.mutateAsync({ requestId, data });
      toast.success("Payment details saved.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Save failed.");
    }
  };

  const onProcess = async () => {
    try {
      await processPayment.mutateAsync(requestId);
      toast.success("Payment processed. Record is now locked.");
      onProcessed?.();
    } catch (err: unknown) {
      setConfirmOpen(false);
      toast.error(err instanceof Error ? err.message : "Process failed.");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSave)} className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field
          label="Payment Date"
          required
          tooltip="The date the payment was made to the supplier."
          error={errors.payment_date?.message}
          type="date"
          disabled={disabled}
          {...register("payment_date")}
        />
        <Field
          label="Bank"
          required
          error={errors.bank?.message}
          type="text"
          disabled={disabled}
          {...register("bank")}
        />
        <Field
          label="Payment Reference Number"
          required
          tooltip="The bank transaction reference or cheque number for this payment."
          error={errors.payment_reference_number?.message}
          type="text"
          disabled={disabled}
          {...register("payment_reference_number")}
        />
        <Field
          label="Payment Status"
          required
          error={errors.payment_status?.message}
          variant="select"
          disabled={disabled}
          {...register("payment_status")}
        >
          {/* Placeholder is not selectable — an explicit status must be picked. */}
          <option value="" disabled>— Select status —</option>
          {PAYMENT_STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </Field>
      </div>
      <Field
        label="Accounts Remarks"
        tooltip="Internal notes visible to your team. Not shown to the merchandiser."
        variant="textarea"
        rows={3}
        disabled={disabled}
        {...register("accounts_remarks")}
      />

      {/* Ship Date — stays interactive even when locked: payment is processed
          (which locks the record) long before the goods actually ship. Recording
          the real ship date here is what stops Cost of Fund accrual. */}
      <div className="pt-4 border-t border-border space-y-3">
        <div>
          <p className="text-sm font-medium text-foreground">Ship Date</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            The actual date the goods were shipped. Recording it stops Cost of Fund
            accrual — it can be entered or corrected even after the record is locked.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <input
            type="date"
            value={shipDate}
            onChange={(e) => setShipDate(e.target.value)}
            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <Button
            type="button"
            onClick={onSaveShipDate}
            disabled={!shipDate || saveShipDate.isPending}
            className="w-full sm:w-auto"
          >
            {saveShipDate.isPending ? "Saving…" : existing?.ship_date ? "Update Ship Date" : "Save Ship Date"}
          </Button>
        </div>
      </div>

      {/* TT Copy — stays interactive even when locked: the flow is process
          (locks the record) → then upload the bank's TT copy. In tranche mode
          uploads happen per tranche; a legacy request-level link still shows. */}
      {(!trancheMode || ttCopyUrl) && (
      <div className="pt-4 border-t border-border space-y-3">
        <div>
          <p className="text-sm font-medium text-foreground">TT Copy</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {trancheMode
              ? "Request-level TT copy from before tranche-level payments."
              : "Upload the bank's TT copy (PDF or image, max 10 MB). It is saved to Google Drive and the link is shared with the merchandiser automatically."}
          </p>
        </div>

        {ttCopyUrl && (
          <a
            href={ttCopyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-secondary text-secondary-foreground text-xs font-medium hover:bg-muted transition-colors"
          >
            View TT copy{ttCopyFilename ? ` — ${ttCopyFilename}` : ""}
            <ExternalLink className="h-3 w-3" />
          </a>
        )}

        {!readOnly && !trancheMode && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            className="flex-1 text-sm text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border file:border-border file:bg-secondary file:text-secondary-foreground file:text-xs file:font-medium file:cursor-pointer hover:file:bg-muted"
          />
          <Button
            type="button"
            onClick={onUploadTtCopy}
            disabled={!selectedFile || uploading}
            className="w-full sm:w-auto"
          >
            {uploading ? "Uploading…" : ttCopyUrl ? "Replace TT Copy" : "Upload TT Copy"}
          </Button>
        </div>
        )}
      </div>
      )}

      {!isLocked && !readOnly && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-2 border-t border-border">
          <Button type="submit" disabled={isSubmitting} className="w-full sm:w-auto">
            {isSubmitting ? "Saving…" : "Save Details"}
          </Button>
          {!trancheMode && (
          <Button
            type="button"
            onClick={() => setConfirmOpen(true)}
            disabled={processPayment.isPending}
            className="w-full sm:w-auto"
          >
            {processPayment.isPending ? "Processing…" : "Process Payment & Lock"}
          </Button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Process payment and lock this record?"
        description="Once processed, this request will be locked. You will not be able to edit payment details. Only a Super Admin can unlock it later."
        confirmLabel="Yes, process & lock"
        onConfirm={onProcess}
      />
    </form>
  );
}
