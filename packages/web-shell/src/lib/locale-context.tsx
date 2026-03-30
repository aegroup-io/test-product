/* eslint-disable react-refresh/only-export-components */
import React, { useMemo, useState } from "react";

import { messages, type AppLocale, type MessageKey } from "./messages";

const STORAGE_KEY = "agentCoreLocale";

function getStoredLocale(): AppLocale {
  if (typeof window === "undefined") {
    return "en-US";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "es-MX" ? "es-MX" : "en-US";
}

type LocaleContextValue = {
  locale: AppLocale;
  setLocale: (value: AppLocale) => void;
  t: (key: MessageKey) => string;
};

const LocaleContext = React.createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(getStoredLocale);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      setLocale: (nextLocale) => {
        setLocaleState(nextLocale);
        window.localStorage.setItem(STORAGE_KEY, nextLocale);
      },
      t: (key) => messages[locale][key] ?? messages["en-US"][key] ?? key,
    }),
    [locale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = React.useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return context;
}
