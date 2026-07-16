"use client";

import { getBackendBaseURL } from "@/core/config";

import { getAuthHeaders } from "./token";

const ADMIN_USERS_PREFIX = "/api/admin/users";

async function adminFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const base = getBackendBaseURL();
  const url = base ? `${base}${path}` : path;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
    ...((options.headers as Record<string, string>) ?? {}),
  };
  return fetch(url, { ...options, headers });
}

export interface UserListItem {
  id: string;
  username: string;
  email: string;
  real_name?: string;
  phone?: string;
  organization_id?: string;
  department_id?: string;
  organization_name?: string;
  department_name?: string;
  is_superuser: boolean;
  is_active: boolean;
  data_permission_level: string;
  last_login_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserListResponse {
  items: UserListItem[];
  total: number;
  page: number;
  page_size: number;
}

export async function listUsers(params: {
  page?: number;
  page_size?: number;
  username?: string;
  is_active?: boolean;
}): Promise<UserListResponse> {
  const sp = new URLSearchParams();
  if (params.page != null) sp.set("page", String(params.page));
  if (params.page_size != null) sp.set("page_size", String(params.page_size));
  if (params.username != null && params.username !== "")
    sp.set("username", params.username);
  if (params.is_active != null) sp.set("is_active", String(params.is_active));
  const q = sp.toString();
  const res = await adminFetch(`${ADMIN_USERS_PREFIX}${q ? `?${q}` : ""}`);
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

export async function getUser(id: string): Promise<Record<string, unknown>> {
  const res = await adminFetch(`${ADMIN_USERS_PREFIX}/${id}`);
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

export interface CreateUserBody {
  username: string;
  email: string;
  password: string;
  real_name?: string;
  phone?: string;
  organization_id?: string;
  department_id?: string;
  is_superuser?: boolean;
  is_active?: boolean;
  data_permission_level?: string;
  role_ids?: string[];
}

export async function createUser(
  body: CreateUserBody,
): Promise<Record<string, unknown>> {
  const res = await adminFetch(ADMIN_USERS_PREFIX, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

export interface UpdateUserBody {
  email?: string;
  password?: string;
  real_name?: string;
  phone?: string;
  organization_id?: string;
  department_id?: string;
  is_superuser?: boolean;
  is_active?: boolean;
  data_permission_level?: string;
  role_ids?: string[];
}

export async function updateUser(
  id: string,
  body: UpdateUserBody,
): Promise<Record<string, unknown>> {
  const res = await adminFetch(`${ADMIN_USERS_PREFIX}/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  return res.json();
}

export async function deleteUser(id: string): Promise<void> {
  const res = await adminFetch(`${ADMIN_USERS_PREFIX}/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
}
