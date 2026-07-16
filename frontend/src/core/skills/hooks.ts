import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { enableSkill, updateSkillMetadata, uploadSkillFolder } from "./api";

import { loadSkills } from ".";

export function useSkills() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills"],
    queryFn: () => loadSkills(),
  });
  return { skills: data ?? [], isLoading, error };
}

export function useEnableSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      enabled,
    }: {
      skillName: string;
      enabled: boolean;
    }) => {
      await enableSkill(skillName, enabled);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useUploadSkillFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      files,
      visibility,
      group_name,
      agent_ids,
    }: {
      files: File[];
      visibility?: "user" | "org";
      group_name?: string;
      agent_ids?: string[];
    }) => uploadSkillFolder(files, { visibility, group_name, agent_ids }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useUpdateSkillMetadata() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillId,
      visibility,
      group_name,
      enabled,
      agent_ids,
    }: {
      skillId: string;
      visibility?: "user" | "org";
      group_name?: string | null;
      enabled?: boolean;
      agent_ids?: string[];
    }) =>
      updateSkillMetadata(skillId, {
        visibility,
        group_name,
        enabled,
        agent_ids,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}
