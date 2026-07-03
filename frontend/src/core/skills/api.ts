import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
import { getAuthHeaders } from "@/core/auth";

import type { Skill } from "./type";

export async function loadSkills(): Promise<Skill[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/skills`, {
    headers: getAuthHeaders(),
  });
  const json = (await res.json().catch(() => ({}))) as { skills?: Skill[] };
  if (!res.ok) throw new Error((json as { detail?: string }).detail ?? res.statusText);
  return json.skills ?? [];
}

export async function enableSkill(skillName: string, enabled: boolean) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        enabled,
      }),
    },
  );
  return response.json();
}

export interface InstallSkillRequest {
  thread_id: string;
  path: string;
}

export interface InstallSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
}

export async function installSkill(
  request: InstallSkillRequest,
): Promise<InstallSkillResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/install`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    // Handle HTTP error responses (4xx, 5xx)
    const errorData = await response.json().catch(() => ({}));
    const errorMessage =
      errorData.detail ?? `HTTP ${response.status}: ${response.statusText}`;
    return {
      success: false,
      skill_name: "",
      message: errorMessage,
    };
  }

  return response.json();
}

export interface UploadSkillFolderResponse {
  success: boolean;
  skill_name: string;
  file_count: number;
  message: string;
}

export async function uploadSkillFolder(
  files: File[],
  options?: {
    visibility?: "user" | "org";
    group_name?: string;
    agent_ids?: string[];
  },
): Promise<UploadSkillFolderResponse> {
  if (!files.length) {
    return {
      success: false,
      skill_name: "",
      file_count: 0,
      message: "未检测到上传文件。",
    };
  }

  const formData = new FormData();
  for (const file of files) {
    const relativePath =
      (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
      file.name;
    formData.append("files", file);
    formData.append("relative_paths", relativePath);
  }
  formData.append("visibility", options?.visibility ?? "user");
  if (options?.group_name) formData.append("group_name", options.group_name);
  for (const aid of options?.agent_ids ?? []) {
    formData.append("agent_ids", aid);
  }

  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/custom/upload`,
    {
      method: "POST",
      headers: {
        ...getAuthHeaders(),
      },
      body: formData,
    },
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const errorMessage =
      errorData.detail ?? `HTTP ${response.status}: ${response.statusText}`;
    return {
      success: false,
      skill_name: "",
      file_count: 0,
      message: errorMessage,
    };
  }

  return response.json();
}

export async function updateSkillMetadata(
  skillId: string,
  payload: {
    visibility?: "user" | "org";
    group_name?: string | null;
    enabled?: boolean;
    agent_ids?: string[];
  },
): Promise<{ success: boolean; skill: Skill }> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillId}/metadata`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(payload),
    },
  );
  const data = (await response.json().catch(() => ({}))) as {
    success?: boolean;
    skill?: Skill;
    detail?: string;
  };
  if (!response.ok) {
    throw new Error(data.detail ?? response.statusText);
  }
  return {
    success: Boolean(data.success),
    skill: data.skill as Skill,
  };
}

export async function getSkillByName(skillName: string): Promise<Skill> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${encodeURIComponent(skillName)}`,
    {
      headers: getAuthHeaders(),
    },
  );
  const data = (await response.json().catch(() => ({}))) as Skill & { detail?: string };
  if (!response.ok) {
    throw new Error(data.detail ?? response.statusText);
  }
  return data;
}
