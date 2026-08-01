import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Sign-in Required — Sunshine",
  description:
    "The public Supplier Advance Payment Request form has been retired. Sign in to raise a request.",
};

export default function PublicFormLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
