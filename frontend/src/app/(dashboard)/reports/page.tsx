"use client";

import { useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { Download, FileSpreadsheet, FileText, FileType, X } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const REPORT_TYPES = [
  {
    value: "requests",
    label: "Supplier Advance Payment Requests",
    desc: "All Supplier Advance Payment Request records including payment and analytics data",
    columns: ["Key", "Request Date", "Select Supplier", "Select Customer", "Vertical/Category", "Currency", "Deposit Amount", "Deposit (%)", "Total Supplier Proforma Invoice Amount", "ETD", "Payment Terms", "Payment Status", "Staff", "Supplier Invoice Number", "Sunshine Invoice Number", "Rate", "Remarks", "Staff Email", "Payment Date", "Bank", "Payment Ref #", "Bank Payment Status", "Ship Date", "Actual ETD", "Accounts Remarks", "ETD (Grace) Overdue Days", "Cost of Fund"],
  },
  {
    // UAT Aug 2026, item 1 — the exact columns Accounts paste into the bank
    // ledger sheet (deposit tracker columns G–K + N).
    value: "bank-ledger",
    label: "Bank Ledger",
    desc: "Bank ledger extract — the exact columns used on the bank ledger sheet",
    columns: ["Supplier", "Supplier Proforma Invoice No.", "Sunshine Invoice No.", "Selected Customer", "Currency", "Deposit Amount"],
  },
  {
    value: "payments",
    label: "Payments",
    desc: "Payment details and processing status",
    columns: ["Request #", "Supplier", "Payment Date", "Bank", "Reference #", "Payment Status", "Ship Date", "Accounts Remarks"],
  },
  {
    value: "suppliers",
    label: "Supplier Summary",
    desc: "Suppliers and default history",
    columns: ["Supplier", "Total Requests", "Total Deposit Amount", "Active Defaults", "Outstanding Amount", "Default Reason", "Flagged Date", "Resolved Date"],
  },
  {
    value: "delays",
    label: "Delay Report",
    desc: "Overdue shipments and ETD breaches",
    columns: ["Request #", "Supplier", "Grace ETD", "ETD Overdue (days)", "Payment Date", "Ship Date", "Pmt→Ship (days)", "Status"],
  },
  {
    value: "cost-of-fund",
    label: "Cost of Fund",
    desc: "Cost of fund exposure per request",
    columns: ["Request #", "Supplier", "Deposit Amount", "Currency", "Cost of Fund Amount", "Delay Days"],
  },
];

const FORMATS = [
  { value: "excel", label: "Excel (.xlsx)", icon: FileSpreadsheet },
  { value: "csv", label: "CSV", icon: FileText },
  { value: "pdf", label: "PDF", icon: FileType },
];

const MIME: Record<string, string> = {
  excel: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  csv: "text/csv",
  pdf: "application/pdf",
};

const EXT: Record<string, string> = {
  excel: "xlsx",
  csv: "csv",
  pdf: "pdf",
};

// Quick date presets
function isoDate(d: Date): string {
  return d.toLocaleDateString("en-CA");
}

const PRESETS = [
  {
    label: "Today",
    range: () => {
      const t = isoDate(new Date());
      return { from: t, to: t };
    },
  },
  {
    label: "Last 7 days",
    range: () => {
      const to = new Date();
      const from = new Date(to);
      from.setDate(from.getDate() - 6);
      return { from: isoDate(from), to: isoDate(to) };
    },
  },
  {
    label: "Last 30 days",
    range: () => {
      const to = new Date();
      const from = new Date(to);
      from.setDate(from.getDate() - 29);
      return { from: isoDate(from), to: isoDate(to) };
    },
  },
  {
    label: "Last 3 months",
    range: () => {
      const to = new Date();
      const from = new Date(to);
      from.setMonth(from.getMonth() - 3);
      return { from: isoDate(from), to: isoDate(to) };
    },
  },
  {
    label: "This year",
    range: () => {
      const to = new Date();
      const from = new Date(to.getFullYear(), 0, 1);
      return { from: isoDate(from), to: isoDate(to) };
    },
  },
];

const DATE_FIELDS = [
  { value: "created", label: "Request Date" },
  { value: "modified", label: "Last Modified" },
  { value: "payment_date", label: "Payment Date" },
];

export default function ReportsPage() {
  const [reportType, setReportType] = useState("requests");
  const [format, setFormat] = useState("excel");
  const [downloading, setDownloading] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [dateField, setDateField] = useState("created");

  const today = isoDate(new Date());
  const selectedReport = REPORT_TYPES.find((r) => r.value === reportType);

  function applyPreset(label: string, range: () => { from: string; to: string }) {
    if (activePreset === label) {
      // Toggle off
      setDateFrom("");
      setDateTo("");
      setActivePreset(null);
    } else {
      const { from, to } = range();
      setDateFrom(from);
      setDateTo(to);
      setActivePreset(label);
    }
  }

  function clearDates() {
    setDateFrom("");
    setDateTo("");
    setActivePreset(null);
  }

  const handleDownload = async () => {
    if (dateFrom && dateTo && dateFrom > dateTo) {
      toast.error('"From" date must be on or before the "To" date.');
      return;
    }
    setDownloading(true);
    try {
      const params = new URLSearchParams({ format });
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      if (reportType === "requests" && dateField !== "created") {
        params.set("date_field", dateField);
      }

      const res = await api.get(`/reports/${reportType}?${params}`, {
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(
        new Blob([res.data as BlobPart], { type: MIME[format] })
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `adt-${reportType}-${new Date().toISOString().slice(0, 10)}.${EXT[format]}`;
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success("Report downloaded.");
    } catch {
      toast.error("Failed to generate report.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"]}>
      <TopNav title="Reports" />
      <main className="flex-1 overflow-auto p-4 md:p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Report Type</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {REPORT_TYPES.map((rt) => (
                <label
                  key={rt.value}
                  className={cn(
                    "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                    reportType === rt.value
                      ? "border-primary bg-secondary"
                      : "border-border hover:border-foreground/30"
                  )}
                >
                  <input
                    type="radio"
                    name="reportType"
                    value={rt.value}
                    checked={reportType === rt.value}
                    onChange={() => setReportType(rt.value)}
                    className="mt-0.5"
                  />
                  <div>
                    <p className="text-sm font-medium text-foreground">{rt.label}</p>
                    <p className="text-xs text-muted-foreground">{rt.desc}</p>
                  </div>
                </label>
              ))}
            </CardContent>
          </Card>

          {/* Column preview */}
          {selectedReport && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Columns in this report</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {selectedReport.columns.map((col) => (
                    <span
                      key={col}
                      className="inline-flex items-center text-xs px-2 py-1 rounded-md bg-muted text-muted-foreground border border-border"
                    >
                      {col}
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Export Format</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                {FORMATS.map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setFormat(value)}
                    className={cn(
                      "flex flex-col items-center gap-2 p-4 rounded-lg border transition-colors",
                      format === value
                        ? "border-primary bg-secondary text-foreground"
                        : "border-border hover:border-foreground/30 text-muted-foreground"
                    )}
                  >
                    <Icon className="h-6 w-6" />
                    <span className="text-xs font-medium">{label}</span>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Date filters */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Date Filter</CardTitle>
                {(dateFrom || dateTo) && (
                  <button
                    onClick={clearDates}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" /> Clear
                  </button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Quick presets */}
              <div>
                <p className="text-xs text-muted-foreground mb-2">Quick select</p>
                <div className="flex flex-wrap gap-2">
                  {PRESETS.map(({ label, range }) => (
                    <button
                      key={label}
                      type="button"
                      onClick={() => applyPreset(label, range)}
                      className={cn(
                        "text-xs px-3 py-1.5 rounded-full border transition-colors",
                        activePreset === label
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Date field selector — Supplier Advance Payment Requests only */}
              {reportType === "requests" && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2">Filter date by</p>
                  <div className="flex gap-2">
                    {DATE_FIELDS.map((f) => (
                      <button
                        key={f.value}
                        type="button"
                        onClick={() => setDateField(f.value)}
                        className={cn(
                          "text-xs px-3 py-1.5 rounded-full border transition-colors",
                          dateField === f.value
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground"
                        )}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Manual From / To */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="date-from">From</Label>
                  <Input
                    id="date-from"
                    type="date"
                    value={dateFrom}
                    max={dateTo || today}
                    onChange={(e) => {
                      setDateFrom(e.target.value);
                      setActivePreset(null);
                    }}
                  />
                </div>
                <div>
                  <Label htmlFor="date-to">To</Label>
                  <Input
                    id="date-to"
                    type="date"
                    value={dateTo}
                    min={dateFrom || undefined}
                    max={today}
                    onChange={(e) => {
                      setDateTo(e.target.value);
                      setActivePreset(null);
                    }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Button
            onClick={handleDownload}
            disabled={downloading}
            size="lg"
            className="w-full gap-2"
          >
            <Download className="h-5 w-5" />
            {downloading ? "Generating…" : "Download Report"}
          </Button>
        </div>
      </main>
    </RoleGuard>
  );
}
