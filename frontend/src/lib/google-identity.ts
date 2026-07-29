// Loads Google Identity Services (GIS) on demand for the sign-in popup.

const GIS_SRC = "https://accounts.google.com/gsi/client";

let gisPromise: Promise<void> | null = null;

export function loadGoogleIdentity(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Google Identity can only load in the browser"));
  }
  if (window.google?.accounts?.oauth2) return Promise.resolve();

  if (!gisPromise) {
    gisPromise = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GIS_SRC;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        gisPromise = null; // allow a retry on the next click
        reject(new Error("Failed to load Google sign-in"));
      };
      document.head.appendChild(script);
    });
  }
  return gisPromise;
}
