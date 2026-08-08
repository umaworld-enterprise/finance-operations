"use client";

import { useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { formatDate, formatDateTime } from "@/lib/utils";
import { ArrowLeft, Filter, X, Download, Monitor, Globe } from "lucide-react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface AuditLog {
  id: string;
  entity_name: string;
  entity_id: string;
  field_name?: string;
  old_value?: string;
  new_value?: string;
  action: string;
  changed_by_email?: string;
  changed_by_name?: string;
  changed_at: string;
  ip_address?: string;
  user_agent?: string;
}

const ACTION_COLORS: Record<string, string> = {
  CREATE:        "bg-primary text-primary-foreground",
  UPDATE:        "bg-primary/10 text-primary",
  DELETE:        "bg-destructive/10 text-destructive",
  STATUS_CHANGE: "bg-secondary text-secondary-foreground",
  LOGIN:         "bg-background text-muted-foreground border border-border",
  AI_QUERY:      "bg-foreground/10 text-foreground",
};

const ENTITY_OPTIONS = [
  "deposit_requests", "payment_details", "users", "suppliers",
  "customers", "verticals", "defaulted_suppliers", "system_config", "ai_bi",
];
const ACTION_OPTIONS = ["CREATE", "UPDATE", "DELETE", "STATUS_CHANGE", "LOGIN", "AI_QUERY"];

function useAuditLogs(
  page: number,
  entity: string,
  action: string,
  fromDate: string,
  toDate: string,
) {
  return useQuery<{ items: AuditLog[]; total: number }>({
    queryKey: ["audit-logs", page, entity, action, fromDate, toDate],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "50",
        ...(entity && { entity }),
        ...(action && { action }),
        ...(fromDate && { from_date: fromDate }),
        ...(toDate && { to_date: toDate }),
      });
      const res = await api.get<{ items: AuditLog[]; total: number }>(
        `/admin/audit-logs?${params.toString()}`
      );
      return res.data;
    },
    staleTime: 2 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
  });
}

function downloadCSV(items: AuditLog[]) {
  const cols = ["changed_at", "action", "entity_name", "field_name", "old_value", "new_value", "changed_by_name", "changed_by_email", "ip_address", "user_agent"];
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [cols.join(","), ...items.map(r => cols.map(c => esc((r as any)[c])).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `audit-log-${Date.now()}.csv`; a.click();
  URL.revokeObjectURL(url);
}

// ── Detail dialog shown when a row is clicked ─────────────────────────────────

function AuditDetailDialog({
  log,
  onClose,
}: {
  log: AuditLog | null;
  onClose: () => void;
}) {
  if (!log) return null;

  const actionCls = ACTION_COLORS[log.action] ?? "bg-muted text-muted-foreground";

  return (
    <Dialog open={!!log} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-w-lg w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${actionCls}`}>
              {log.action}
            </span>
            <span className="font-mono text-sm text-muted-foreground">{log.entity_name}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Timestamp */}
          <Row label="Timestamp" value={formatDateTime(log.changed_at)} />

          {/* Entity */}
          <Row label="Entity" value={log.entity_name} />
          <Row label="Entity ID" value={log.entity_id} mono />

          {/* Field change */}
          {log.field_name && <Row label="Field" value={log.field_name} mono />}

          {(log.old_value || log.new_value) && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Old value</p>
                <p className="text-sm text-muted-foreground bg-muted rounded-md px-3 py-2 break-all font-mono">
                  {log.old_value ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">New value</p>
                <p className="text-sm text-foreground bg-muted rounded-md px-3 py-2 break-all font-mono">
                  {log.new_value ?? "—"}
                </p>
              </div>
            </div>
          )}

          {/* User */}
          <div className="border-t border-border pt-3 space-y-2">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Performed by</p>
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-full bg-muted flex items-center justify-center text-xs font-semibold text-foreground shrink-0">
                {(log.changed_by_name ?? log.changed_by_email ?? "?")[0].toUpperCase()}
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">{log.changed_by_name ?? "—"}</p>
                <p className="text-xs text-muted-foreground">{log.changed_by_email ?? "—"}</p>
              </div>
            </div>
          </div>

          {/* IP + User Agent */}
          <div className="border-t border-border pt-3 space-y-2">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">Request metadata</p>
            <div className="flex items-start gap-2">
              <Globe className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
              <p className="text-sm font-mono text-foreground">{log.ip_address ?? "Not captured"}</p>
            </div>
            {log.user_agent && (
              <div className="flex items-start gap-2">
                <Monitor className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                <p className="text-xs text-muted-foreground break-all leading-relaxed">{log.user_agent}</p>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <p className="text-xs text-muted-foreground w-24 shrink-0 mt-0.5">{label}</p>
      <p className={`text-sm text-foreground break-all ${mono ? "font-mono text-xs" : ""}`}>{value}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AuditLogsPage() {
  const [page, setPage] = useState(1);
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const { data, isLoading } = useAuditLogs(page, entity, action, fromDate, toDate);
  const totalPages = data ? Math.ceil(data.total / 50) : 1;
  const hasFilters = !!(entity || action || fromDate || toDate);

  function clearFilters() {
    setEntity(""); setAction(""); setFromDate(""); setToDate(""); setPage(1);
  }

  return (
    <RoleGuard allowedRoles={["super_admin", "finance_admin"]}>
      <TopNav title="Audit Logs" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <Link
            href="/admin"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Back to admin
          </Link>
          <div className="flex gap-2">
            {data?.items && data.items.length > 0 && (
              <Button size="sm" variant="outline" onClick={() => downloadCSV(data.items)}>
                <Download className="h-3.5 w-3.5 mr-1" /> Export
              </Button>
            )}
            <Button
              size="sm"
              variant={showFilters ? "secondary" : "outline"}
              onClick={() => setShowFilters(f => !f)}
            >
              <Filter className="h-3.5 w-3.5 mr-1" />
              Filters {hasFilters && <span className="ml-1 bg-primary text-primary-foreground rounded-full px-1.5 text-[10px]">{[entity,action,fromDate,toDate].filter(Boolean).length}</span>}
            </Button>
          </div>
        </div>

        {/* Filter bar */}
        {showFilters && (
          <Card className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Entity</label>
                <select
                  value={entity}
                  onChange={e => { setEntity(e.target.value); setPage(1); }}
                  className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
                >
                  <option value="">All entities</option>
                  {ENTITY_OPTIONS.map(e => <option key={e} value={e}>{e}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">Action</label>
                <select
                  value={action}
                  onChange={e => { setAction(e.target.value); setPage(1); }}
                  className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
                >
                  <option value="">All actions</option>
                  {ACTION_OPTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">From date</label>
                <Input type="date" value={fromDate} onChange={e => { setFromDate(e.target.value); setPage(1); }} className="h-8 text-sm" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground font-medium">To date</label>
                <Input type="date" value={toDate} onChange={e => { setToDate(e.target.value); setPage(1); }} className="h-8 text-sm" />
              </div>
            </div>
            {hasFilters && (
              <button onClick={clearFilters} className="mt-2 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                <X className="h-3 w-3" /> Clear all filters
              </button>
            )}
          </Card>
        )}

        <Card className="overflow-hidden">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Audit Trail</CardTitle>
            <CardDescription>
              {data?.total ?? "—"} {hasFilters ? "filtered" : "total"} entries · most recent first · click any row for full details
            </CardDescription>
          </CardHeader>

          {/* Mobile card view */}
          <div className="md:hidden divide-y divide-border">
            {isLoading ? (
              <div className="p-4 text-sm text-muted-foreground text-center">Loading…</div>
            ) : (data?.items ?? []).length === 0 ? (
              <div className="p-4 text-sm text-muted-foreground text-center">No entries found.</div>
            ) : (
              (data?.items ?? []).map(log => (
                <button
                  key={log.id}
                  type="button"
                  onClick={() => setSelectedLog(log)}
                  className="w-full text-left p-4 space-y-2 hover:bg-muted/50 transition-colors active:bg-muted"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${ACTION_COLORS[log.action] ?? "bg-muted text-muted-foreground"}`}>
                      {log.action}
                    </span>
                    <span className="text-xs text-muted-foreground">{formatDate(log.changed_at)}</span>
                  </div>
                  <div className="text-sm font-medium text-foreground">
                    {log.entity_name}
                    {log.field_name && <span className="text-muted-foreground font-normal"> · {log.field_name}</span>}
                  </div>
                  {(log.old_value || log.new_value) && (
                    <div className="text-xs space-y-0.5">
                      {log.old_value && <div className="text-muted-foreground line-through truncate">{log.old_value}</div>}
                      {log.new_value && <div className="text-foreground truncate">{log.new_value}</div>}
                    </div>
                  )}
                  <div className="text-xs text-muted-foreground flex items-center gap-2">
                    <span>{log.changed_by_name ?? log.changed_by_email ?? "—"}</span>
                    {log.ip_address && <span className="font-mono">{log.ip_address}</span>}
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Desktop table view */}
          <div className="hidden md:block overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-36">Timestamp</TableHead>
                  <TableHead className="w-32">Action</TableHead>
                  <TableHead>Entity</TableHead>
                  <TableHead className="hidden lg:table-cell">Field</TableHead>
                  <TableHead className="hidden lg:table-cell">Old Value</TableHead>
                  <TableHead>New Value</TableHead>
                  <TableHead className="hidden xl:table-cell">User</TableHead>
                  <TableHead className="hidden xl:table-cell">IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableSkeleton rows={10} cols={8} />
                ) : (data?.items ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-muted-foreground py-10">
                      No entries found{hasFilters ? " for the current filters" : ""}.
                    </TableCell>
                  </TableRow>
                ) : (
                  (data?.items ?? []).map(log => (
                    <TableRow
                      key={log.id}
                      onClick={() => setSelectedLog(log)}
                      className="cursor-pointer hover:bg-muted/50 transition-colors"
                    >
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatDate(log.changed_at)}
                      </TableCell>
                      <TableCell>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${ACTION_COLORS[log.action] ?? "bg-muted text-muted-foreground"}`}>
                          {log.action}
                        </span>
                      </TableCell>
                      <TableCell className="text-xs">
                        <span className="font-medium">{log.entity_name}</span>
                        <span className="text-muted-foreground ml-1 font-mono text-[10px]">{log.entity_id.slice(0, 8)}</span>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground font-mono hidden lg:table-cell">{log.field_name ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[140px] truncate hidden lg:table-cell" title={log.old_value}>{log.old_value ?? "—"}</TableCell>
                      <TableCell className="text-xs text-foreground max-w-[160px] truncate" title={log.new_value}>{log.new_value ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground hidden xl:table-cell">
                        <div>{log.changed_by_name ?? "—"}</div>
                        <div className="text-[10px]">{log.changed_by_email}</div>
                      </TableCell>
                      <TableCell className="text-[10px] text-muted-foreground font-mono hidden xl:table-cell">{log.ip_address ?? "—"}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-border flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Page {page} of {totalPages} · {data?.total} entries</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Prev</Button>
                <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>Next</Button>
              </div>
            </div>
          )}
        </Card>
      </main>

      <AuditDetailDialog log={selectedLog} onClose={() => setSelectedLog(null)} />
    </RoleGuard>
  );
}
