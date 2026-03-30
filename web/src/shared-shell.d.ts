declare module "@aegroup/agent-core-web-shell" {
  import type { ComponentType, ReactNode } from "react";

  export type ShellBranding = {
    title?: string;
    kicker?: string;
    logoLightSrc?: string;
    logoDarkSrc?: string;
  };

  export type ShellMode = "full" | "settings-content";
  export type ThemePreference = "light" | "dark" | "system";
  export type ShellSettingsExtensionProps = {
    user: {
      user_id: string;
      username?: string | null;
      roles: string[];
      permissions: string[];
      feature_flags: string[];
      org_ids: string[];
      default_org_id?: string | null;
      claims: Record<string, unknown>;
    } | null;
    organizations: Array<{
      org_id: string;
      name: string;
      slug: string;
      documentation_visibility?: string | null;
      created_at: string;
      updated_at: string;
    }>;
    selectedOrg: {
      org_id: string;
      name: string;
      slug: string;
      documentation_visibility?: string | null;
      created_at: string;
      updated_at: string;
    } | null;
    hasPermission: (permission: string) => boolean;
  };
  export type ShellSettingsExtension = {
    path: string;
    label: string;
    icon: ComponentType<{ className?: string }>;
    render: (props: ShellSettingsExtensionProps) => ReactNode;
  };

  export function AgentCoreShellApp(props: {
    branding?: ShellBranding;
    mode?: ShellMode;
    settingsExtensions?: ShellSettingsExtension[];
  }): JSX.Element;
  export function LocaleProvider(props: { children: ReactNode }): JSX.Element;
  export function ThemeProvider(props: { children: ReactNode }): JSX.Element;
  export function useTheme(): {
    preference: ThemePreference;
    resolvedDark: boolean;
    setPreference: (value: ThemePreference) => void;
  };
}

declare module "@aegroup/agent-core-web-shell/styles.css";
