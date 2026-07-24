"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TopNav } from "@/components/layout/TopNav";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  BrainCircuit, CheckCircle2, XCircle, Loader2, ArrowLeft, Eye, EyeOff,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

interface AIConfig {
  provider: string;
  model: string | null;
  api_key_set: boolean;
}

interface UserRow {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  ai_access_enabled: boolean;
}

const PROVIDER_LABELS: Record<string, string> = {
  groq: "Groq — llama-3.3-70b (fast, free tier)",
  openai: "OpenAI — GPT-4o Mini",
  claude: "Claude — Haiku (Anthropic)",
};

const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super Admin",
  finance_admin: "Finance Admin",
  accounts_team: "Accounts Team",
  merchandiser: "Merchandiser",
};

async function fetchConfig(): Promise<AIConfig> {
  const res = await api.get("/ai/config");
  return res.data;
}

async function fetchUsers(): Promise<UserRow[]> {
  const res = await api.get("/masters/users");
  return res.data;
}

async function saveConfig(data: {
  provider: string;
  api_key: string;
  model?: string;
}): Promise<AIConfig> {
  const res = await api.put("/ai/config", data);
  return res.data;
}

async function toggleAccess({
  userId,
  enabled,
}: {
  userId: string;
  enabled: boolean;
}) {
  const res = await api.patch(`/ai/users/${userId}/access`, {
    ai_access_enabled: enabled,
  });
  return res.data;
}

export default function AISettingsPage() {
  const qc = useQueryClient();

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ["ai-config"],
    queryFn: fetchConfig,
  });

  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const configMutation = useMutation({
    mutationFn: saveConfig,
    onSuccess: (data) => {
      // Update cache immediately so UI reflects the new state without waiting for refetch
      qc.setQueryData(["ai-config"], data);
      qc.invalidateQueries({ queryKey: ["ai-config"] });
      toast.success("AI settings saved.");
      setApiKey("");
    },
    onError: (e: any) =>
      toast.error(e?.message || "Failed to save settings."),
  });

  const accessMutation = useMutation({
    mutationFn: toggleAccess,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e: any) =>
      toast.error(e?.message || "Failed to update access."),
  });

  function handleSaveConfig() {
    const p = provider || config?.provider || "groq";
    if (!apiKey) {
      toast.error("Please enter the API key.");
      return;
    }
    configMutation.mutate({
      provider: p,
      api_key: apiKey,
      model: model || undefined,
    });
  }

  function handleToggle(user: UserRow) {
    if (user.role === "super_admin") return;
    setTogglingId(user.id);
    accessMutation.mutate(
      { userId: user.id, enabled: !user.ai_access_enabled },
      { onSettled: () => setTogglingId(null) }
    );
  }

  const activeProvider = provider || config?.provider || "groq";
  const nonAdmins = users.filter(
    (u) => u.role !== "super_admin" && u.is_active
  );

  const placeholderModel =
    activeProvider === "groq"
      ? "llama-3.3-70b-versatile"
      : activeProvider === "openai"
      ? "gpt-4o-mini"
      : "claude-haiku-4-5-20251001";

  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <TopNav title="AI BI Settings" />
      <main className="p-6 max-w-4xl mx-auto space-y-6">
        <Link
          href="/admin"
          className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 w-fit"
        >
          <ArrowLeft className="h-4 w-4" /> Back to admin
        </Link>

        <div className="flex items-center gap-3">
          <div className="bg-primary p-2 rounded-lg">
            <BrainCircuit className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">AI BI Assistant Settings</h1>
            <p className="text-sm text-muted-foreground">
              Configure the AI provider and control who can use the assistant.
            </p>
          </div>
        </div>

        {/* Provider config */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">AI Provider Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {configLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground text-sm">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading…
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                Current:
                <span className="font-medium text-foreground">
                  {PROVIDER_LABELS[config?.provider ?? "groq"] ??
                    config?.provider}
                </span>
                {config?.api_key_set ? (
                  <span className="text-green-600 flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Key set
                  </span>
                ) : (
                  <span className="text-destructive flex items-center gap-1">
                    <XCircle className="h-3.5 w-3.5" /> No key configured
                  </span>
                )}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Provider select */}
              <div className="space-y-1.5">
                <Label htmlFor="provider-select">Provider</Label>
                <select
                  id="provider-select"
                  value={activeProvider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="groq">Groq — llama-3.3-70b (fast, free)</option>
                  <option value="openai">OpenAI — GPT-4o Mini</option>
                  <option value="claude">Claude — Haiku (Anthropic)</option>
                </select>
              </div>

              {/* Model override */}
              <div className="space-y-1.5">
                <Label htmlFor="model-input">
                  Model override{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="model-input"
                  placeholder={placeholderModel}
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                />
              </div>

              {/* API key */}
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="api-key-input">
                  API Key <span className="text-destructive">*</span>
                </Label>
                <div className="relative">
                  <Input
                    id="api-key-input"
                    type={showKey ? "text" : "password"}
                    placeholder="Paste your API key here"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Stored securely in system_config. Re-enter to update.
                </p>
              </div>
            </div>

            <Button
              onClick={handleSaveConfig}
              disabled={configMutation.isPending || !apiKey}
            >
              {configMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Saving…
                </>
              ) : (
                "Save Configuration"
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Per-user access */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">User Access Control</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Super Admins always have access. Toggle access for other users
              below. Access is enforced server-side — it cannot be bypassed.
            </p>

            {usersLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading users…
              </div>
            ) : nonAdmins.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No non-admin users found.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="hidden sm:table-cell">Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead className="text-right">AI Access</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {nonAdmins.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium">
                        {u.full_name}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-muted-foreground text-sm">
                        {u.email}
                      </TableCell>
                      <TableCell>
                        <span className="text-xs bg-muted px-2 py-0.5 rounded-full">
                          {ROLE_LABELS[u.role] ?? u.role}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        {togglingId === u.id ? (
                          <Loader2 className="h-4 w-4 animate-spin ml-auto text-muted-foreground" />
                        ) : (
                          <Switch
                            checked={u.ai_access_enabled}
                            onCheckedChange={() => handleToggle(u)}
                            disabled={togglingId !== null}
                          />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>
    </RoleGuard>
  );
}
