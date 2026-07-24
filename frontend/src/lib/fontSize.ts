import type { FontSize } from "@/types";

export const FONT_SIZE_STORAGE_KEY = "adt-font-size";

// Tailwind is rem-based, so scaling the root font-size scales the whole app.
export const FONT_SIZE_MAP: Record<FontSize, string> = {
  default: "100%",
  large: "112.5%",
  xlarge: "125%",
};

export function applyFontSize(size: FontSize): void {
  if (typeof document === "undefined") return;
  document.documentElement.style.fontSize = FONT_SIZE_MAP[size] ?? "100%";
}

export function getStoredFontSize(): FontSize {
  if (typeof window === "undefined") return "default";
  const stored = window.localStorage.getItem(FONT_SIZE_STORAGE_KEY);
  return stored === "large" || stored === "xlarge" ? stored : "default";
}

export function storeFontSize(size: FontSize): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(FONT_SIZE_STORAGE_KEY, size);
}
