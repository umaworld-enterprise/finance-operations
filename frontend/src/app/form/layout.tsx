import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Submit Supplier Advance Payment Request — Sunshine",
  description: "Submit a Supplier Advance Payment Request to the Sunshine finance team.",
};

export default function PublicFormLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
