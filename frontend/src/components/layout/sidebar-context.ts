"use client";

import { createContext } from "react";

export interface SidebarContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

export const SidebarContext = createContext<SidebarContextValue>({
  open: false,
  setOpen: () => {},
});
