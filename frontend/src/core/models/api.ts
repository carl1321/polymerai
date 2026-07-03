import { getBackendBaseURL } from "../config";
import { getAuthHeaders } from "@/core/auth";
import { isStaticWebsiteOnly } from "../static-mode";

import type { ModelsResponse } from "./types";

const STATIC_MODELS_RESPONSE: ModelsResponse = {
  models: [],
  token_usage: { enabled: false },
};

export async function loadModels(): Promise<ModelsResponse> {
  if (isStaticWebsiteOnly()) {
    return STATIC_MODELS_RESPONSE;
  }

  const res = await fetch(`${getBackendBaseURL()}/api/models`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    return { models: [], token_usage: { enabled: false } };
  }
  const data = (await res.json()) as Partial<ModelsResponse>;
  return {
    models: data.models ?? [],
    token_usage: data.token_usage ?? { enabled: false },
  };
}
