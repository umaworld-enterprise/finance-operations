import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Finance Operations",
    short_name: "Finance Ops",
    description: "Supplier advance deposit management — track payments, shipments, and supplier risk.",
    start_url: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#ffffff",
    theme_color: "#1a3155",
    categories: ["finance", "business", "productivity"],
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
