/* eslint-disable react-refresh/only-export-components */
import React, { useEffect, useLayoutEffect, useMemo, useState } from "react";

export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "agentCoreTheme";

function getStoredPreference(): ThemePreference {
  if (typeof window === "undefined") {
    return "system";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") {
    return stored;
  }
  return "system";
}

function getSystemDark() {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(isDark: boolean) {
  document.documentElement.classList.toggle("dark", isDark);
}

type ThemeContextValue = {
  preference: ThemePreference;
  resolvedDark: boolean;
  setPreference: (value: ThemePreference) => void;
};

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(getStoredPreference);
  const [systemDark, setSystemDark] = useState(getSystemDark);

  const resolvedDark = useMemo(
    () => (preference === "system" ? systemDark : preference === "dark"),
    [preference, systemDark],
  );

  useLayoutEffect(() => {
    applyTheme(resolvedDark);
  }, [resolvedDark]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, preference);
  }, [preference]);

  useEffect(() => {
    if (!window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const value = useMemo(
    () => ({
      preference,
      resolvedDark,
      setPreference,
    }),
    [preference, resolvedDark],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = React.useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
