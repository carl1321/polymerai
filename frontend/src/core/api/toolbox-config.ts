/**
 * 工具箱用 useConfig 占位：与 agentic_workflow 同接口，供 ToolExecutor 使用。
 * 返回 config 与 loading，无后端时 config 为 null。
 */

export interface ModelInfo {
  name: string;
  [key: string]: unknown;
}

export interface ToolboxConfigModels {
  [key: string]: ModelInfo[] | undefined;
}

export interface ToolboxConfig {
  models?: ToolboxConfigModels;
  [key: string]: unknown;
}

export function useToolboxConfig(): { config: ToolboxConfig | null; loading: boolean } {
  return { config: null, loading: false };
}
