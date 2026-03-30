import {
  BrowserAuthError,
  PublicClientApplication,
  type AuthenticationResult,
} from "@azure/msal-browser";

const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID as string | undefined;
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID as string | undefined;
const redirectUri =
  (import.meta.env.VITE_ENTRA_REDIRECT_URI as string | undefined) ??
  window.location.origin;
const scope = import.meta.env.VITE_ENTRA_SCOPE as string | undefined;
const authFlow =
  (import.meta.env.VITE_AUTH_FLOW as string | undefined)?.toLowerCase() ??
  "popup";

const authority = tenantId
  ? `https://login.microsoftonline.com/${tenantId}/v2.0`
  : undefined;

const msal = new PublicClientApplication({
  auth: {
    clientId: clientId ?? "",
    authority,
    redirectUri,
  },
  cache: {
    cacheLocation: "localStorage",
  },
});

let initialized = false;
let redirectResult: AuthenticationResult | null = null;

async function ensureMsal() {
  if (!initialized) {
    await msal.initialize();
    try {
      redirectResult = await msal.handleRedirectPromise();
      if (redirectResult?.account) {
        msal.setActiveAccount(redirectResult.account);
      }
    } catch {
      redirectResult = null;
    }
    initialized = true;
  }
  return msal;
}

export function isAuthConfigured() {
  return Boolean(clientId && tenantId && scope);
}

function getScopes() {
  return scope ? [scope] : [];
}

function clearInteractionStatus() {
  if (typeof window === "undefined") {
    return;
  }
  const storages = [window.sessionStorage, window.localStorage];
  storages.forEach((storage) => {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key && key.includes("interaction.status")) {
        keys.push(key);
      }
    }
    keys.forEach((key) => storage.removeItem(key));
  });
}

export async function initAuth() {
  await ensureMsal();
  return redirectResult;
}

export async function login() {
  if (!isAuthConfigured()) {
    return null;
  }
  const app = await ensureMsal();
  if (authFlow === "redirect") {
    await app.loginRedirect({ scopes: getScopes() });
    return null;
  }
  try {
    const result = await app.loginPopup({ scopes: getScopes() });
    if (result?.account) {
      app.setActiveAccount(result.account);
    }
    return result;
  } catch (error) {
    if (
      error instanceof BrowserAuthError &&
      error.errorCode === "interaction_in_progress"
    ) {
      clearInteractionStatus();
      return await app.loginPopup({ scopes: getScopes() });
    }
    if (
      error instanceof BrowserAuthError &&
      ["popup_window_error", "popup_window_timeout", "user_cancelled"].includes(
        error.errorCode,
      )
    ) {
      throw error;
    }
    if (
      error instanceof Error &&
      error.message.includes("Cross-Origin-Opener-Policy")
    ) {
      await app.loginRedirect({ scopes: getScopes() });
      return null;
    }
    if (!(error instanceof BrowserAuthError)) {
      await app.loginRedirect({ scopes: getScopes() });
      return null;
    }
    throw error;
  }
}

export async function logout() {
  if (!isAuthConfigured()) {
    return;
  }
  const app = await ensureMsal();
  const account = app.getActiveAccount() ?? app.getAllAccounts()[0] ?? null;
  app.setActiveAccount(null);
  await app.logoutRedirect({
    account: account ?? undefined,
    postLogoutRedirectUri: window.location.origin,
  });
}

export async function acquireToken() {
  if (!isAuthConfigured()) {
    return null;
  }
  const app = await ensureMsal();
  const account = app.getActiveAccount() ?? app.getAllAccounts()[0];
  if (!account) {
    return null;
  }
  try {
    const result = await app.acquireTokenSilent({
      account,
      scopes: getScopes(),
    });
    return result.accessToken;
  } catch (error) {
    if (
      error instanceof BrowserAuthError &&
      error.errorCode === "interaction_in_progress"
    ) {
      return null;
    }
    throw error;
  }
}

export async function getAccountLabel() {
  if (!isAuthConfigured()) {
    return null;
  }
  const app = await ensureMsal();
  const account = app.getActiveAccount() ?? app.getAllAccounts()[0];
  return account?.name ?? account?.username ?? null;
}
