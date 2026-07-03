export interface Agent {
  id: string;
  name: string;
  description: string;
  model: string | null;
  model_name?: string | null;
  tool_groups: string[] | null;
  skills: string[] | null;
  soul?: string | null;
  knowledge_base_ids?: string[] | null;
  kind?: "dedicated" | "swarm" | null;
  member_dedicated_ids?: string[] | null;
  memory_enabled?: boolean | null;
  visibility?: "user" | "org" | null;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  model?: string | null;
  tool_groups?: string[] | null;
  tool_names?: string[] | null;
  skill_names?: string[] | null;
  kind?: "dedicated" | "swarm" | null;
  member_dedicated_ids?: string[] | null;
  skills?: string[] | null;
  soul?: string;
  memory_enabled?: boolean | null;
  visibility?: "user" | "org" | null;
}

export interface UpdateAgentRequest {
  name?: string | null;
  description?: string | null;
  model?: string | null;
  tool_groups?: string[] | null;
  tool_names?: string[] | null;
  skill_names?: string[] | null;
  kind?: "dedicated" | "swarm" | null;
  member_dedicated_ids?: string[] | null;
  skills?: string[] | null;
  soul?: string | null;
  memory_enabled?: boolean | null;
  visibility?: "user" | "org" | null;
}
