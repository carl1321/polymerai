/**
 * 数据抽取 API 占位：与 agentic_workflow 同接口，便于拷贝 ToolExecutor。
 * 当前环境无数据抽取后端时返回空列表 / 静默失败。
 */

export interface DataExtractionRecord {
  id: string;
  task_id?: string;
  task_name?: string;
  extraction_type: string;
  extraction_step: number;
  file_name?: string;
  file_size?: number;
  file_base64?: string;
  pdf_url?: string;
  model_name?: string;
  categories?: {
    materials: string[];
    processes: string[];
    properties: string[];
  };
  selected_categories?: {
    materials: string[];
    processes: string[];
    properties: string[];
  };
  table_data?: Array<{ material: string; process: string; property: string }>;
  result_json?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface DataExtractionRecordRequest {
  task_name?: string;
  extraction_type?: string;
  extraction_step?: number;
  file_name?: string;
  file_size?: number;
  file_base64?: string;
  pdf_url?: string;
  model_name?: string;
  categories?: { materials: string[]; processes: string[]; properties: string[] };
  selected_categories?: { materials: string[]; processes: string[]; properties: string[] };
  table_data?: Array<{ material: string; process: string; property: string }>;
  result_json?: string;
  metadata?: Record<string, unknown>;
  record_id?: string;
  task_id?: string;
}

export interface DataExtractionRecordListResponse {
  records: DataExtractionRecord[];
  total: number;
  limit: number;
  offset: number;
}

export async function saveExtractionRecord(
  record: DataExtractionRecordRequest,
): Promise<DataExtractionRecord> {
  // 占位：无后端时返回本地模拟记录，便于 UI 不报错
  return {
    id: `stub-${Date.now()}`,
    task_id: record.task_id ?? `task-${Date.now()}`,
    extraction_type: record.extraction_type ?? "material_extraction",
    extraction_step: record.extraction_step ?? 1,
    ...record,
  };
}

export async function getExtractionRecords(
  limit: number = 50,
  offset: number = 0,
  _extraction_type?: string,
): Promise<DataExtractionRecordListResponse> {
  return { records: [], total: 0, limit, offset };
}

export async function getExtractionRecord(_recordId: string): Promise<DataExtractionRecord> {
  throw new Error("数据抽取服务未配置");
}

export async function deleteExtractionRecord(_recordId: string): Promise<void> {
  // no-op
}
