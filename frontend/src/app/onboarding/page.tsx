"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import Image from "next/image";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { LoadingScreen } from "@/components/ui/LoadingScreen";
import type { AppUser } from "@/types";

const ROLE_HOME: Record<string, string> = {
  merchandiser: "/merchandiser",
  accounts_team: "/accounts",
  finance_admin: "/finance",
  super_admin: "/admin",
  head_of_merchandiser: "/hom",
};

// Fixed department list (no master table) — the backend stores a free string,
// so extending this list is a frontend-only change and legacy free-typed
// values in the DB stay valid.
const DEPARTMENTS = [
  "Merchandising",
  "Accounts",
  "Finance",
  "Management",
  "IT",
  "Other",
] as const;

interface FormValues {
  full_name: string;
  secondary_email: string;
  department: string;
}

export default function OnboardingPage() {
  const { user, loading } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<FormValues>();

  useEffect(() => {
    if (user) {
      if (user.onboarding_completed) {
        window.location.href = ROLE_HOME[user.role] ?? "/analytics";
        return;
      }
      setValue("full_name", user.full_name ?? "");
    }
  }, [user, setValue]);

  if (loading) return <LoadingScreen message="Loading…" />;
  if (!user) {
    window.location.href = "/login";
    return <LoadingScreen message="Redirecting…" />;
  }

  const onSubmit = async (values: FormValues) => {
    setSubmitting(true);
    setError(null);
    try {
      await api.patch<AppUser>("/auth/profile", {
        full_name: values.full_name.trim(),
        secondary_email: values.secondary_email.trim() || null,
        department: values.department.trim(),
      });
      window.location.href = ROLE_HOME[user.role] ?? "/analytics";
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-background p-4">
      <Card className="max-w-md w-full p-8 space-y-6">
        <div className="flex flex-col items-center gap-3">
          <div className="bg-white border border-border p-3 rounded-xl shadow-sm">
            <Image
              src="/logo.png"
              alt="Sunshine"
              width={36}
              height={36}
              className="h-9 w-9 object-contain"
              priority
            />
          </div>
          <div className="text-center">
            <h1 className="text-lg font-semibold text-foreground">Complete Your Profile</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Just a few details before you get started.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="full_name">Full Name</Label>
            <Input
              id="full_name"
              {...register("full_name", { required: "Full name is required" })}
              placeholder="Your full name"
            />
            {errors.full_name && (
              <p className="text-xs text-destructive">{errors.full_name.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <Label htmlFor="department">Department</Label>
            <Select
              id="department"
              defaultValue=""
              {...register("department", { required: "Department is required" })}
            >
              <option value="" disabled>Select department</option>
              {DEPARTMENTS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </Select>
            {errors.department && (
              <p className="text-xs text-destructive">{errors.department.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <Label htmlFor="secondary_email">
              Secondary Email{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Input
              id="secondary_email"
              type="email"
              {...register("secondary_email")}
              placeholder="backup@example.com"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive rounded-md bg-destructive/10 px-3 py-2">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitting ? "Saving…" : "Continue to Workspace"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
