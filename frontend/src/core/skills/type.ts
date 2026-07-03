export interface Skill {
  id?: string | null;
  name: string;
  description: string;
  laber_name?: string | null;
  laber_description?: string | null;
  category: string;
  license: string | null;
  enabled: boolean;
  /** Optional display group for UI (e.g. vaspagent). */
  group?: string | null;
  /** Optional list of tool names exposed by this skill. */
  tool_names?: string[] | null;
  visibility?: "user" | "org" | null;
  user_id?: string | null;
  organization_id?: string | null;
  group_name?: string | null;
  agent_ids?: string[] | null;
}
