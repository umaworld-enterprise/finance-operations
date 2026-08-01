"use client";

// The public (login-free) request form was RETIRED in the Aug 2026 change
// batch — deposit requests are now raised through the authenticated in-app
// form only. This page remains so old bookmarks and shared form links
// (/form and /form/[slug]) land on a clear sign-in notice instead of a 404.

import Image from "next/image";
import Link from "next/link";
import { Lock } from "lucide-react";

export default function RetiredPublicFormPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-2xl border border-gray-200 shadow-sm p-10 text-center">
        <div className="flex justify-center mb-5">
          <div className="bg-white border border-gray-200 p-3 rounded-xl shadow-sm">
            <Image src="/logo.png" alt="Sunshine" width={36} height={36} className="h-9 w-9 object-contain" />
          </div>
        </div>
        <Lock className="h-10 w-10 text-gray-400 mx-auto mb-4" />
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Sign-in Required</h1>
        <p className="text-gray-600 text-sm mb-6">
          This form now requires sign-in. The public Supplier Advance Payment
          Request form has been retired — please sign in and raise your request
          from your dashboard.
        </p>
        <Link
          href="/login"
          className="inline-flex w-full items-center justify-center bg-gray-900 text-white rounded-xl px-4 py-3 text-sm font-semibold hover:bg-gray-800 transition-colors"
        >
          Sign in to continue
        </Link>
        <p className="text-xs text-gray-400 mt-4">
          No account? Contact your administrator for access.
        </p>
      </div>
    </div>
  );
}
