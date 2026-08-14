"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SearchInput } from "@/components/ui/SearchInput";
import { Pagination } from "@/components/ui/Pagination";
import { byString, useClientTable } from "@/hooks/useClientTable";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { useUsers, useCreateUser, useUpdateUser } from "@/hooks/useMasters";
import { formatDate, ROLE_LABELS } from "@/lib/utils";
import type { AppUser, UserRole } from "@/types";
import { ArrowLeft, Plus, UserPlus, Copy, Check } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

const ROLES: UserRole[] = ["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"];

const inviteSchema = z.object({
  email: z.string().email("Enter a valid email"),
  full_name: z.string().min(2, "Enter a name"),
  role: z.enum(["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"]),
});
type InviteForm = z.infer<typeof inviteSchema>;

function InviteCard({ email, role, onClose }: { email: string; role: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const appUrl = typeof window !== "undefined" ? window.location.origin : "";
  const roleLabel = ROLE_LABELS[role as keyof typeof ROLE_LABELS] ?? role;
  const message = `Hi,\n\nYou've been added to Finance Operations as ${roleLabel}.\n\nSign in here using your Google account (${email}):\n${appUrl}/login\n\nYour access is ready immediately.`;

  function copy() {
    navigator.clipboard.writeText(message).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="border border-border rounded-xl p-5 bg-muted/30 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Ready to share</p>
        <button onClick={onClose} className="text-xs text-muted-foreground hover:text-foreground">Dismiss</button>
      </div>
      <p className="text-xs text-muted-foreground">Send this message to <span className="font-medium text-foreground">{email}</span> so they can sign in.</p>
      <pre className="text-xs bg-background border border-border rounded-lg p-3 whitespace-pre-wrap text-foreground leading-relaxed font-sans">{message}</pre>
      <button
        onClick={copy}
        className="flex items-center gap-1.5 text-xs font-medium text-foreground border border-border rounded-lg px-3 py-1.5 hover:bg-muted transition-colors"
      >
        {copied ? <><Check className="h-3.5 w-3.5" /> Copied!</> : <><Copy className="h-3.5 w-3.5" /> Copy message</>}
      </button>
    </div>
  );
}

export default function UsersPage() {
  const { data: users = [], isLoading } = useUsers();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<{ id: string; name: string } | null>(null);
  const [lastInvited, setLastInvited] = useState<{ email: string; role: string } | null>(null);
  // Search / sort / pagination (10 Aug 2026, app-wide table controls).
  const userSorts = [
    { value: "name", label: "Name (A–Z)", compare: byString<AppUser>((u) => u.full_name) },
    { value: "role", label: "Role", compare: byString<AppUser>((u) => u.role) },
    { value: "recent-login", label: "Recent login first", compare: byString<AppUser>((u) => u.last_login_at ?? "", true) },
  ];
  const userTable = useClientTable(users, {
    searchHaystack: (u) => [u.full_name, u.email, ROLE_LABELS[u.role]],
    sortOptions: userSorts,
    pageSize: 25,
  });
  const { search, setSearch } = userTable;
  const term = search.trim().toLowerCase();
  const filteredUsers = userTable.visible;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InviteForm>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { role: "merchandiser" },
  });

  const onInvite = async (data: InviteForm) => {
    try {
      await createUser.mutateAsync(data);
      setLastInvited({ email: data.email, role: data.role });
      reset({ role: "merchandiser", email: "", full_name: "" });
      setDialogOpen(false);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to add user.");
    }
  };

  const changeRole = async (id: string, role: UserRole) => {
    setBusyId(id);
    try {
      await updateUser.mutateAsync({ id, payload: { role } });
      toast.success("Role updated.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update role.");
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (id: string, is_active: boolean) => {
    setBusyId(id);
    try {
      await updateUser.mutateAsync({ id, payload: { is_active } });
      toast.success(is_active ? "User activated." : "User deactivated.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update user.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav title="User Management" subtitle="Add team members and assign roles" />
      <main className="flex-1 overflow-auto p-4 md:p-6 space-y-4">
        <Link
          href="/admin"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to admin
        </Link>

        {lastInvited && (
          <InviteCard
            email={lastInvited.email}
            role={lastInvited.role}
            onClose={() => setLastInvited(null)}
          />
        )}

        <Card className="overflow-hidden">
          <CardHeader>
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
              <div>
                <CardTitle>Team Members</CardTitle>
                <CardDescription>
                  Add a person by email and assign a role. They get access the first time they sign in with Google.
                </CardDescription>
              </div>
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" className="shrink-0 w-full sm:w-auto">
                    <Plus className="h-4 w-4 mr-1" /> Add User
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <div className="flex items-center gap-2.5">
                      <div className="bg-muted p-2 rounded-lg">
                        <UserPlus className="h-4 w-4 text-foreground" />
                      </div>
                      <div>
                        <DialogTitle>Add Team Member</DialogTitle>
                        <DialogDescription>
                          Use the exact Google account email they will sign in with.
                        </DialogDescription>
                      </div>
                    </div>
                  </DialogHeader>

                  <form onSubmit={handleSubmit(onInvite)} className="space-y-4">
                    <Field
                      label="Email"
                      required
                      tooltip="The Google account email this person will use to sign in."
                      error={errors.email?.message}
                      type="email"
                      placeholder="person@company.com"
                      {...register("email")}
                    />
                    <Field
                      label="Full Name"
                      required
                      error={errors.full_name?.message}
                      type="text"
                      placeholder="Jane Doe"
                      {...register("full_name")}
                    />
                    <Field
                      label="Role"
                      required
                      tooltip="Super Admin: full access. Finance Admin: analytics & reports. Accounts Team: payment processing. Merchandiser: submit own requests."
                      variant="select"
                      {...register("role")}
                    >
                      {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                    </Field>
                    <DialogFooter>
                      <DialogClose asChild>
                        <Button type="button" variant="outline" className="w-full sm:w-auto">Cancel</Button>
                      </DialogClose>
                      <Button type="submit" disabled={isSubmitting} className="w-full sm:w-auto">
                        {isSubmitting ? "Adding…" : "Add User"}
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
            <div className="mt-3 flex flex-col sm:flex-row gap-2">
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder="Search by name, email or role…"
                className="sm:max-w-md flex-1"
              />
              <select
                value={userTable.sort}
                onChange={(e) => userTable.setSort(e.target.value)}
                aria-label="Sort users"
                className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring sm:w-52"
              >
                {userSorts.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </CardHeader>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="hidden md:table-cell">Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden lg:table-cell">Last Login</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableSkeleton rows={6} cols={6} />
              ) : filteredUsers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">
                    {term ? `No users match "${search.trim()}".` : "No users yet."}
                  </TableCell>
                </TableRow>
              ) : (
                filteredUsers.map((u) => (
                  <TableRow key={u.id} className={!u.is_active ? "opacity-60" : ""}>
                    <TableCell className="font-medium text-foreground">{u.full_name}</TableCell>
                    <TableCell className="hidden md:table-cell text-muted-foreground">{u.email}</TableCell>
                    <TableCell>
                      <Select
                        value={u.role}
                        disabled={busyId === u.id}
                        onChange={(e) => changeRole(u.id, e.target.value as UserRole)}
                        className="w-auto text-xs py-1"
                      >
                        {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.is_active ? "default" : "secondary"}>
                        {u.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-muted-foreground text-xs">
                      {u.last_login_at ? formatDate(u.last_login_at) : "Never"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant={u.is_active ? "outline" : "secondary"}
                        disabled={busyId === u.id}
                        onClick={() => {
                          if (u.is_active) {
                            setDeactivateTarget({ id: u.id, name: u.full_name });
                          } else {
                            toggleActive(u.id, true);
                          }
                        }}
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
          <div className="px-4">
            <Pagination
              page={userTable.page}
              totalPages={userTable.totalPages}
              total={userTable.total}
              pageSize={userTable.pageSize}
              onChange={userTable.setPage}
            />
          </div>
        </Card>
      </main>

      <ConfirmDialog
        open={deactivateTarget !== null}
        onOpenChange={(open) => !open && setDeactivateTarget(null)}
        title={`Deactivate ${deactivateTarget?.name ?? "this user"}?`}
        description="They will lose access immediately and cannot sign in until reactivated."
        confirmLabel="Yes, deactivate"
        destructive
        onConfirm={() => deactivateTarget && toggleActive(deactivateTarget.id, false)}
      />
    </RoleGuard>
  );
}
