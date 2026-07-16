"use client";

import { useEffect } from "react";

import { installGlobal401Redirect } from "@/core/auth/install-global-401";

export function Global401RedirectInstaller() {
  useEffect(() => {
    installGlobal401Redirect();
  }, []);

  return null;
}
