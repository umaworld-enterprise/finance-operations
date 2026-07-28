import type { Metadata, ReactNode } from "next";

export const metadata: Metadata = {
  title: "Submit Supplier Advance Payment Request — Sunshine",
  description: "Submit a Supplier Advance Payment Request to the Sunshine finance team.",
};

export default function PublicFormLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
