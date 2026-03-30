import type { SettingResponse } from "./operator-types";

export const PRODUCT_DEFAULTS_SETTING_KEY = "orcha.product_defaults";
export const SELECTED_ORG_STORAGE_KEY = "agentCoreSelectedOrgId";

export type ProductOnboardingDefaults = {
  github: {
    statusField: string;
    readyStatus: string;
    doneStatus: string;
  };
  baseline: {
    channel: string;
  };
  execution: {
    profile: string;
  };
  activation: {
    requiredSecretKeys: string[];
  };
};

export type ProductOnboardingDefaultsRecord = {
  loaded: boolean;
  setting: SettingResponse | null;
  rawValue: Record<string, unknown>;
  defaults: ProductOnboardingDefaults;
  error: string | null;
};

export const DEFAULT_PRODUCT_ONBOARDING_DEFAULTS: ProductOnboardingDefaults = {
  github: {
    statusField: "Status",
    readyStatus: "Todo",
    doneStatus: "Done",
  },
  baseline: {
    channel: "stable",
  },
  execution: {
    profile: "standard-python",
  },
  activation: {
    requiredSecretKeys: [],
  },
};

export function cloneProductOnboardingDefaults(
  defaults: ProductOnboardingDefaults = DEFAULT_PRODUCT_ONBOARDING_DEFAULTS,
): ProductOnboardingDefaults {
  return {
    github: { ...defaults.github },
    baseline: { ...defaults.baseline },
    execution: { ...defaults.execution },
    activation: {
      requiredSecretKeys: [...defaults.activation.requiredSecretKeys],
    },
  };
}

export function normalizeOnboardingSecretKeys(keys: string[]) {
  return Array.from(
    new Set(
      keys
        .map((key) => key.trim())
        .filter(Boolean),
    ),
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? (JSON.parse(JSON.stringify(value)) as Record<string, unknown>) : {};
}

function readRecord(root: Record<string, unknown>, key: string) {
  return isRecord(root[key]) ? (root[key] as Record<string, unknown>) : null;
}

function readString(root: Record<string, unknown> | null, key: string, fallback: string) {
  const value = root?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function ensureRecord(root: Record<string, unknown>, key: string) {
  const existing = readRecord(root, key);
  if (existing) {
    return existing;
  }
  const next: Record<string, unknown> = {};
  root[key] = next;
  return next;
}

function pruneEmptyRecords(root: Record<string, unknown>) {
  for (const [key, value] of Object.entries(root)) {
    if (!isRecord(value)) {
      continue;
    }
    pruneEmptyRecords(value);
    if (!Object.keys(value).length) {
      delete root[key];
    }
  }
  return root;
}

export function extractProductOnboardingDefaults(value: unknown): ProductOnboardingDefaults {
  const root = cloneRecord(value);
  const github = readRecord(root, "github");
  const baseline = readRecord(root, "baseline");
  const execution = readRecord(root, "execution");
  const activation = readRecord(root, "activation");
  const requiredSecretKeys = Array.isArray(activation?.required_secret_keys)
    ? normalizeOnboardingSecretKeys(
        activation.required_secret_keys.filter((entry): entry is string => typeof entry === "string"),
      )
    : DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.activation.requiredSecretKeys;

  return {
    github: {
      statusField: readString(
        github,
        "status_field",
        DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.github.statusField,
      ),
      readyStatus: readString(
        github,
        "ready_status",
        DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.github.readyStatus,
      ),
      doneStatus: readString(
        github,
        "done_status",
        DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.github.doneStatus,
      ),
    },
    baseline: {
      channel: readString(
        baseline,
        "channel",
        DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.baseline.channel,
      ),
    },
    execution: {
      profile: readString(
        execution,
        "profile",
        DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.execution.profile,
      ),
    },
    activation: {
      requiredSecretKeys,
    },
  };
}

export function buildProductOnboardingDefaultsValue(
  existingValue: unknown,
  defaults: ProductOnboardingDefaults,
): Record<string, unknown> {
  const root = cloneRecord(existingValue);
  const github = ensureRecord(root, "github");
  const baseline = ensureRecord(root, "baseline");
  const execution = ensureRecord(root, "execution");
  const activation = ensureRecord(root, "activation");
  delete github.installation_id;
  delete github.installation_label;

  github.status_field =
    defaults.github.statusField.trim() || DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.github.statusField;
  github.ready_status =
    defaults.github.readyStatus.trim() || DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.github.readyStatus;
  github.done_status =
    defaults.github.doneStatus.trim() || DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.github.doneStatus;
  baseline.channel = defaults.baseline.channel.trim() || DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.baseline.channel;
  execution.profile =
    defaults.execution.profile.trim() || DEFAULT_PRODUCT_ONBOARDING_DEFAULTS.execution.profile;
  activation.required_secret_keys = normalizeOnboardingSecretKeys(defaults.activation.requiredSecretKeys);

  return pruneEmptyRecords(root);
}

export function buildProductOnboardingDefaultsRecord(
  setting: SettingResponse | null,
): ProductOnboardingDefaultsRecord {
  if (setting && !isRecord(setting.value_json)) {
    return {
      loaded: true,
      setting,
      rawValue: {},
      defaults: cloneProductOnboardingDefaults(),
      error: `Setting ${PRODUCT_DEFAULTS_SETTING_KEY} must be a JSON object before Orcha can use it as workspace defaults.`,
    };
  }

  return {
    loaded: true,
    setting,
    rawValue: cloneRecord(setting?.value_json),
    defaults: extractProductOnboardingDefaults(setting?.value_json),
    error: null,
  };
}

export function createUnloadedProductOnboardingDefaultsRecord(): ProductOnboardingDefaultsRecord {
  return {
    loaded: false,
    setting: null,
    rawValue: {},
    defaults: cloneProductOnboardingDefaults(),
    error: null,
  };
}

export function createErroredProductOnboardingDefaultsRecord(
  error: string,
): ProductOnboardingDefaultsRecord {
  return {
    loaded: true,
    setting: null,
    rawValue: {},
    defaults: cloneProductOnboardingDefaults(),
    error,
  };
}
