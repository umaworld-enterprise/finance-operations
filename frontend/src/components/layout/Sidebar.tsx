"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useContext, useEffect } from "react";
import { SidebarContext } from "@/components/layout/sidebar-context";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  ArrowLeftRight,
  BarChart3,
  BrainCircuit,
  ClipboardList,
  CreditCard,
  FileText,
  LayoutDashboard,
  LogOut,
  ScrollText,
  Settings,
  ShieldAlert,
  Users,
  UserCog,
} from "lucide-react";
import type { UserRole } from "@/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  roles: UserRole[];
  group: "main" | "admin";
}

const NAV_ITEMS: NavItem[] = [
  { href: "/admin",         label: "Admin Overview", icon: LayoutDashboard, roles: ["super_admin"],                                                                      group: "main"  },
  { href: "/accounts",      label: "Payment Queue",  icon: CreditCard,      roles: ["accounts_team", "super_admin"],                                                     group: "main"  },
  { href: "/adjust-invoices", label: "Adjust Invoices", icon: ArrowLeftRight, roles: ["accounts_team", "super_admin", "finance_admin"],                                    group: "main"  },
  { href: "/merchandiser",  label: "My Requests",    icon: ClipboardList,   roles: ["merchandiser"],                                                                     group: "main"  },
  { href: "/hom",           label: "HoM Dashboard",  icon: UserCog,         roles: ["head_of_merchandiser", "super_admin"],                                              group: "main"  },
  { href: "/finance",       label: "Supplier Risk",  icon: ShieldAlert,     roles: ["finance_admin", "super_admin"],                                                     group: "main"  },
  { href: "/analytics",     label: "Analytics",      icon: BarChart3,       roles: ["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"], group: "main" },
  { href: "/reports",       label: "Reports",        icon: FileText,        roles: ["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"], group: "main" },
  { href: "/settings",      label: "Settings",       icon: Settings,        roles: ["super_admin", "finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"], group: "main" },
  { href: "/admin/users",   label: "Users",          icon: Users,           roles: ["super_admin"],                                                                      group: "admin" },
  { href: "/admin/audit",   label: "Audit Logs",     icon: ScrollText,      roles: ["super_admin", "finance_admin"],                                                     group: "admin" },
  { href: "/admin/ai",      label: "AI Settings",    icon: BrainCircuit,    roles: ["super_admin"],                                                                      group: "admin" },
];

function getInitials(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((n) => n[0])
    .join("")
    .toUpperCase();
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const { open, setOpen } = useContext(SidebarContext);

  useEffect(() => {
    setOpen(false);
  }, [pathname, setOpen]);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const visibleItems = NAV_ITEMS.filter(
    (item) => user && item.roles.includes(user.role)
  );

  const mainItems  = visibleItems.filter((i) => i.group === "main");
  const adminItems = visibleItems.filter((i) => i.group === "admin");

  const bestMatch = visibleItems
    .filter((i) => pathname === i.href || pathname.startsWith(i.href + "/"))
    .sort((a, b) => b.href.length - a.href.length)[0];

  const renderItems = (items: NavItem[]) =>
    items.map((item) => {
      const active = bestMatch?.href === item.href;
      const Icon = item.icon;
      return (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all relative touch-manipulation",
            active
              ? "bg-white/15 text-white font-medium"
              : "text-blue-200/60 hover:bg-white/8 hover:text-white"
          )}
        >
          {active && (
            <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-white rounded-full" />
          )}
          <Icon
            className={cn(
              "h-4 w-4 shrink-0 transition-colors",
              active ? "text-white" : "text-blue-200/50 group-hover:text-white"
            )}
          />
          {item.label}
        </Link>
      );
    });

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      )}

      <div
        id="sidebar-drawer"
        className={cn(
          "w-60 flex flex-col min-h-screen shrink-0",
          "fixed inset-y-0 left-0 z-40 transition-transform duration-300 ease-in-out",
          // Keep the logo and sign-out clear of the status bar / home
          // indicator in the installed PWA; env() is 0 in regular browsers.
          "pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]",
          open ? "translate-x-0" : "-translate-x-full",
          "lg:static lg:z-auto lg:translate-x-0 lg:transition-none"
        )}
        style={{ background: "hsl(215, 55%, 12%)" }}
      >
        {/* Logo */}
        <div className="px-4 py-5 border-b border-white/10">
          <Image
            src="/logo-finance-ops.png"
            alt="Sunshine — Finance Operations"
            width={208}
            height={60}
            className="w-full h-auto"
            priority
          />
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-5 overflow-y-auto">
          {mainItems.length > 0 && (
            <div className="space-y-0.5">
              <p className="px-3 mb-2 text-[10px] font-semibold tracking-wide text-blue-200/40 uppercase">
                Menu
              </p>
              {renderItems(mainItems)}
            </div>
          )}

          {adminItems.length > 0 && (
            <div className="mt-6 space-y-0.5">
              <div className="border-t border-white/10 mb-4" />
              <p className="px-3 mb-2 text-[10px] font-semibold tracking-wide text-blue-200/40 uppercase">
                Admin
              </p>
              {renderItems(adminItems)}
            </div>
          )}
        </nav>

        {/* User footer */}
        {user && (
          <div className="px-3 py-4 border-t border-white/10">
            <div className="flex items-center gap-2.5">
              <Avatar className="h-8 w-8 shrink-0 border border-white/20">
                <AvatarFallback className="text-xs font-semibold bg-white/15 text-white">
                  {getInitials(user.full_name ?? user.email ?? "U")}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white truncate">
                  {user.full_name ?? user.email}
                </p>
                <p className="text-[10px] text-blue-200/60 truncate capitalize">
                  {user.role.replace(/_/g, " ")}
                </p>
              </div>
              <button
                onClick={signOut}
                aria-label="Sign out"
                title="Sign out"
                className="p-1.5 rounded-lg text-blue-200/50 hover:text-white hover:bg-white/10 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/30"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
