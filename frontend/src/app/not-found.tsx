import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4 text-center bg-background">
      <div className="bg-white border border-border p-3 rounded-xl mb-6 shadow-sm">
        <Image
          src="/logo.png"
          alt="Sunshine"
          width={32}
          height={32}
          className="h-8 w-8 object-contain"
        />
      </div>
      <div className="bg-muted rounded-full p-4 mb-4">
        <FileQuestion className="h-8 w-8 text-foreground" />
      </div>
      <h2 className="text-lg font-semibold text-foreground">Page not found</h2>
      <p className="text-sm text-muted-foreground mt-1 max-w-sm">
        The page you&apos;re looking for doesn&apos;t exist or may have been moved.
      </p>
      <Button asChild className="mt-4">
        <Link href="/">Go home</Link>
      </Button>
    </div>
  );
}
