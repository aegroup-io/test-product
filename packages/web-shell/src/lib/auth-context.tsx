/* eslint-disable react-refresh/only-export-components */
import React, { useMemo } from "react";

import type { UserInfo } from "../api/types";

type AuthContextValue = {
  userInfo: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  hasPermission: (permission: string) => boolean;
  hasFeatureFlag: (featureFlag: string) => boolean;
  refresh: () => Promise<void>;
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  user,
  isLoading,
  authDisabled,
  refresh,
}: {
  children: React.ReactNode;
  user: UserInfo | null;
  isLoading: boolean;
  authDisabled: boolean;
  refresh: () => Promise<void>;
}) {
  const value = useMemo<AuthContextValue>(
    () => ({
      userInfo: user,
      isAuthenticated: authDisabled ? true : Boolean(user),
      isLoading,
      hasPermission: (permission) => (authDisabled ? true : (user?.permissions ?? []).includes(permission)),
      hasFeatureFlag: (featureFlag) => (authDisabled ? true : (user?.feature_flags ?? []).includes(featureFlag)),
      refresh,
    }),
    [authDisabled, isLoading, refresh, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
