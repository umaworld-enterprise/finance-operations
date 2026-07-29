"use client";

import { useState } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ArrowLeft, Copy, Link2, Plus, Trash2, Loader2, Check } from "lucide-react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface FormLink {
  id: string;
  slug: string;
  label: string;
  is_active: boolean;
  created_at: string;
}

const APP_URL =
  (typeof window !== "undefined" ? window.location.origin : null) ??
  process.env.NEXT_PUBLIC_APP_URL ??
  "";

function buildUrl(slug: string) {
  return `${APP_URL}/form/${slug}`;
}

async function fetchLinks(): Promise<FormLink[]> {
  const res = await api.get<FormLink[]>("/admin/form-links");
  return res.data;
}

export default function FormLinksPage() {
  const qc = useQueryClient();
  const { data: links = [], isLoading } = useQuery({ queryKey: ["form-links"], queryFn: fetchLinks, staleTime: 5 * 60 * 1000 });
  const [newLabel, setNewLabel] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async (body: { label: string; slug: string }) => {
      const res = await api.post("/admin/form-links", body);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["form-links"] });
      toast.success("Form link created.");
      setNewLabel("");
      setNewSlug("");
      setDialogOpen(false);
    },
    onError: (e: unknown) => {
      toast.error(e instanceof Error ? e.message : "Failed to create link");
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
      await api.patch(`/admin/form-links/${id}`, { is_active });
    },
    onMutate: async ({ id, is_active }) => {
      await qc.cancelQueries({ queryKey: ["form-links"] });
      const previous = qc.getQueryData<FormLink[]>(["form-links"]);
      qc.setQueryData<FormLink[]>(["form-links"], (old) =>
        old?.map((l) => (l.id === id ? { ...l, is_active } : l)) ?? []
      );
      return { previous };
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["form-links"] }),
    onError: (_err, _vars, context) => {
      if (context?.previous !== undefined) {
        qc.setQueryData(["form-links"], context.previous);
      }
      toast.error("Failed to update link");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/admin/form-links/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["form-links"] });
      toast.success("Link deleted.");
    },
    onError: () => toast.error("Failed to delete link"),
  });

  const copyUrl = (link: FormLink) => {
    navigator.clipboard.writeText(buildUrl(link.slug));
    setCopiedId(link.id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const slugify = (val: string) =>
    val.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <div className="min-h-screen bg-background">
        <TopNav title="Form Links" />
        <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
          <div className="flex items-center gap-3">
            <Link href="/admin" className="text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div>
              <h1 className="text-xl font-semibold text-foreground">Shareable Form Links</h1>
              <p className="text-sm text-muted-foreground">
                Each link opens the same public form. Use different slugs to track where submissions came from.
              </p>
            </div>
          </div>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-4">
              <div>
                <CardTitle className="text-base">Active Links</CardTitle>
                <CardDescription>Anyone with a link can submit a Supplier Advance Payment Request — no login required.</CardDescription>
              </div>
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm">
                    <Plus className="h-4 w-4 mr-1" />
                    New Link
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Create Form Link</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 pt-2">
                    <div className="space-y-1">
                      <Label htmlFor="link-label">Label</Label>
                      <Input
                        id="link-label"
                        value={newLabel}
                        onChange={(e) => {
                          setNewLabel(e.target.value);
                          if (!newSlug || newSlug === slugify(newLabel)) {
                            setNewSlug(slugify(e.target.value));
                          }
                        }}
                        placeholder="e.g. Africa Q3 Campaign"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="link-slug">URL Slug</Label>
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground whitespace-nowrap">/form/</span>
                        <Input
                          id="link-slug"
                          value={newSlug}
                          onChange={(e) => setNewSlug(slugify(e.target.value))}
                          placeholder="africa-q3"
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Lowercase letters, numbers, and hyphens only (3–50 characters).
                      </p>
                    </div>
                    <Button
                      className="w-full"
                      onClick={() => createMutation.mutate({ label: newLabel, slug: newSlug })}
                      disabled={!newLabel || newSlug.length < 3 || createMutation.isPending}
                    >
                      {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Create Link
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="flex items-center justify-center py-12 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin mr-2" />
                  Loading…
                </div>
              ) : links.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Link2 className="h-8 w-8 mx-auto mb-2 opacity-40" />
                  <p className="text-sm">No form links yet. Create your first one above.</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Label</TableHead>
                      <TableHead>Full URL</TableHead>
                      <TableHead className="text-center">Active</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {links.map((link) => (
                      <TableRow key={link.id}>
                        <TableCell className="font-medium">{link.label}</TableCell>
                        <TableCell>
                          <span className="text-sm text-muted-foreground font-mono break-all">
                            {buildUrl(link.slug)}
                          </span>
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={link.is_active}
                            onCheckedChange={(val) =>
                              toggleMutation.mutate({ id: link.id, is_active: val })
                            }
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => copyUrl(link)}
                              title="Copy URL"
                            >
                              {copiedId === link.id ? (
                                <Check className="h-4 w-4 text-green-600" />
                              ) : (
                                <Copy className="h-4 w-4" />
                              )}
                            </Button>
                            {link.slug !== "default" && (
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => deleteMutation.mutate(link.id)}
                                disabled={deleteMutation.isPending}
                                title="Delete"
                                className="text-destructive hover:text-destructive"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </RoleGuard>
  );
}
