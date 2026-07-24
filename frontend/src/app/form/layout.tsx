import type { Metadata, ReactNode } from "next";

export const metadata: Metadata = {
  title: "Submit Deposit Request — Sunshine",
  description: "Submit an advance deposit request to the Sunshine finance team.",
};

export default function PublicFormLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
