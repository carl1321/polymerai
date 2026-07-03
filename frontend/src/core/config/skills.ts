/**
 * 统一技能列表：集成 agentic_workflow 项目工具 + deer-flow 本地工具，以 skills 方式展示。
 * 仅用于工具箱列表展示，不包含执行历史。
 */

import type { LucideIcon } from "lucide-react";
import {
  Atom,
  FlaskConical,
  Microscope,
  TrendingUp,
  Globe,
  Search,
  Code,
  Volume2,
  Sparkles,
  FileText,
  Image as ImageIcon,
  Play,
  Terminal,
  FolderOpen,
  FileInput,
  FileOutput,
  Replace,
  Workflow,
  Library,
  Cpu,
} from "lucide-react";

export type SkillCategory = "molecular" | "literature" | "general";

/** 技能详情页参数定义（与 agentic_workflow ToolParameter 一致） */
export interface ToolParameter {
  name: string;
  type: "string" | "number" | "boolean" | "array";
  description: string;
  required: boolean;
  default?: unknown;
  enum?: string[];
}

export interface SkillConfig {
  id: string;
  name: string;
  description: string;
  category: SkillCategory;
  icon: LucideIcon;
  /** 后端工具名（deer-flow 可执行时使用）；来自 agentic_workflow 的仅展示 */
  toolName?: string;
  /** 详情页参数表单（无则仅展示说明） */
  parameters?: ToolParameter[];
}

/** 全部技能：agentic_workflow 工具 + deer-flow 工具 */
export const skills: SkillConfig[] = [
  // ---------- 分子科学（来自 agentic_workflow）----------
  {
    id: "sam_generator",
    name: "SAM分子能力集",
    description: "分子生成、分子可视化、性质预测（HOMO/LUMO/DM）。通过 skill 脚本执行：generate.py / visualize.py / predict.py，无专用工具。",
    category: "molecular",
    icon: Atom,
    // 执行方式：bash 运行 scripts/generate.py、visualize.py、predict.py（见 SKILL.md）
    parameters: [
      {
        name: "scaffold_condition",
        type: "string",
        description: "骨架SMILES，多个用逗号分隔",
        required: true,
        default: "c1ccccc1",
      },
      {
        name: "anchoring_group",
        type: "string",
        description: "锚定基团SMILES",
        required: true,
        default: "O=P(O)(O)",
      },
      { name: "gen_size", type: "number", description: "生成数量", required: false, default: 10 },
    ],
  },
  {
    id: "visualize_molecules",
    name: "分子可视化",
    description: "生成分子结构图",
    category: "molecular",
    icon: Microscope,
    toolName: "visualize_molecules_tool",
    parameters: [
      { name: "smiles", type: "string", description: "SMILES字符串", required: true },
      { name: "width", type: "number", description: "图片宽度", required: false, default: 800 },
      { name: "height", type: "number", description: "图片高度", required: false, default: 600 },
    ],
  },
  {
    id: "property_predictor",
    name: "性质预测",
    description: "预测分子的物理化学性质（HOMO、LUMO、偶极矩）",
    category: "molecular",
    icon: TrendingUp,
    toolName: "property_predictor_tool",
    parameters: [
      {
        name: "smiles_text",
        type: "string",
        description: "SMILES字符串（可多行，也可以是带编号的列表）",
        required: true,
      },
      {
        name: "properties",
        type: "string",
        description: '要预测的性质，用逗号分隔，如 "HOMO,LUMO,DM"',
        required: false,
        default: "HOMO,LUMO,DM",
      },
    ],
  },
  {
    id: "phase_diagram",
    name: "相图分析",
    description: "基于 Materials Project 的 0 K 能量凸包分析化学体系的稳定相与亚稳相",
    category: "molecular",
    icon: Globe,
    toolName: "phase_diagram_tool",
    parameters: [
      { name: "chemical_system", type: "string", description: "化学体系，如 Li-Fe-P-O", required: true },
      { name: "max_entries", type: "number", description: "最多条目数", required: false, default: 128 },
    ],
  },
  {
    id: "molecular_analysis",
    name: "分子结构分析",
    description: "使用InternLM API分析分子结构，包括化学性质、结构特征等",
    category: "molecular",
    icon: FlaskConical,
    toolName: "molecular_analysis_tool",
    parameters: [{ name: "smiles", type: "string", description: "SMILES字符串", required: true }],
  },
  {
    id: "literature_search",
    name: "文献搜索",
    description: "使用 arXiv 搜索学术文献",
    category: "literature",
    icon: Search,
    toolName: "literature_search_tool",
    parameters: [
      { name: "query", type: "string", description: "搜索查询", required: true },
      { name: "limit", type: "number", description: "返回数量", required: false, default: 10 },
    ],
  },
  {
    id: "python_repl",
    name: "Python代码执行",
    description: "在沙箱环境中执行Python代码",
    category: "general",
    icon: Code,
    toolName: "python_repl_tool",
    parameters: [{ name: "code", type: "string", description: "Python代码", required: true }],
  },
  {
    id: "tts",
    name: "TTS语音",
    description: "文本转语音",
    category: "general",
    icon: Volume2,
    toolName: "tts_tool",
    parameters: [
      { name: "text", type: "string", description: "要转换的文本", required: true },
      { name: "voice", type: "string", description: "语音类型", required: false, default: "female", enum: ["male", "female"] },
    ],
  },
  {
    id: "prompt_optimizer",
    name: "提示词优化",
    description: "基于自定义提示词和问题，使用AI模型生成回答",
    category: "general",
    icon: Sparkles,
    toolName: "prompt_optimizer_tool",
    parameters: [
      { name: "prompt", type: "string", description: "系统提示词", required: true },
      { name: "question", type: "string", description: "用户问题", required: true },
      { name: "model_name", type: "string", description: "模型名称（可选）", required: false },
    ],
  },
  {
    id: "data_extraction",
    name: "数据抽取",
    description: "从PDF或XML文件中提取结构化数据，支持提示词抽取和材料数据抽取两种模式",
    category: "general",
    icon: FileText,
    toolName: "data_extraction_tool",
    parameters: [
      { name: "extraction_type", type: "string", description: "prompt_extraction 或 material_extraction", required: false, default: "prompt_extraction" },
      { name: "extraction_prompt", type: "string", description: "抽取提示词", required: false },
      { name: "json_schema", type: "string", description: "JSON格式定义", required: false },
      { name: "model_name", type: "string", description: "模型名称（可选）", required: false },
    ],
  },
  {
    id: "image_gen",
    name: "文生图",
    description: "根据文本描述生成图片，返回下载链接",
    category: "general",
    icon: ImageIcon,
    toolName: "image_gen_tool",
    parameters: [
      { name: "prompt", type: "string", description: "图片描述", required: true },
      { name: "size", type: "string", description: "图片尺寸", required: false, default: "1024x1024" },
    ],
  },
  {
    id: "ppt_generator",
    name: "PPT生成",
    description: "一句话生成PPT：默认 baoyu 风格整页图幻灯片（大纲→图片→PPTX/PDF），可选文字型 PPT",
    category: "general",
    icon: FileText,
    toolName: "generate_ppt_tool",
    parameters: [
      { name: "engine", type: "string", description: "simple 或 slide_deck", required: false, default: "slide_deck", enum: ["simple", "slide_deck"] },
      { name: "topic", type: "string", description: "一句话主题", required: false },
      { name: "content", type: "string", description: "长文/Markdown（与 topic 二选一）", required: false },
      { name: "style", type: "string", description: "风格", required: false, default: "blueprint" },
      { name: "slides", type: "number", description: "目标页数", required: false, default: 8 },
    ],
  },
  {
    id: "web_search",
    name: "网页搜索",
    description: "使用搜索引擎查询并返回摘要",
    category: "general",
    icon: Search,
    toolName: "web_search",
    parameters: [{ name: "query", type: "string", description: "搜索词", required: true }],
  },
  {
    id: "web_fetch",
    name: "网页抓取",
    description: "抓取指定 URL 的网页内容",
    category: "general",
    icon: Globe,
    toolName: "web_fetch",
    parameters: [{ name: "url", type: "string", description: "网页 URL", required: true }],
  },
  {
    id: "image_search",
    name: "图片搜索",
    description: "根据关键词搜索图片",
    category: "general",
    icon: ImageIcon,
    toolName: "image_search",
    parameters: [{ name: "query", type: "string", description: "图片关键词", required: true }],
  },
  {
    id: "ls",
    name: "列出目录",
    description: "列出目录下的文件与子目录",
    category: "general",
    icon: FolderOpen,
    toolName: "ls",
    parameters: [{ name: "path", type: "string", description: "目录路径", required: false, default: "." }],
  },
  {
    id: "read_file",
    name: "读取文件",
    description: "读取工作区内的文件内容",
    category: "general",
    icon: FileInput,
    toolName: "read_file",
    parameters: [{ name: "path", type: "string", description: "文件路径", required: true }],
  },
  {
    id: "write_file",
    name: "写入文件",
    description: "向工作区内写入文件",
    category: "general",
    icon: FileOutput,
    toolName: "write_file",
    parameters: [
      { name: "path", type: "string", description: "文件路径", required: true },
      { name: "content", type: "string", description: "文件内容", required: true },
    ],
  },
  {
    id: "str_replace",
    name: "字符串替换",
    description: "在文件中查找并替换字符串",
    category: "general",
    icon: Replace,
    toolName: "str_replace",
    parameters: [
      { name: "path", type: "string", description: "文件路径", required: true },
      { name: "old", type: "string", description: "被替换字符串", required: true },
      { name: "new", type: "string", description: "新字符串", required: true },
    ],
  },
  {
    id: "bash",
    name: "执行命令",
    description: "在沙箱中执行 Shell 命令",
    category: "general",
    icon: Terminal,
    toolName: "bash",
    parameters: [{ name: "command", type: "string", description: "Shell 命令", required: true }],
  },
];

/** 常用技能（快捷按钮）：工作流、文献搜索、数据抽取、文生图、PPT生成 */
export const COMMON_SKILL_IDS = ["workflow", "literature_search", "data_extraction", "image_gen", "ppt_generator"] as const;

/** 置顶技能（卡片，与 agentic_workflow 一致）：工作流 + 文献搜索 + 数据抽取 + 文生图 + PPT生成 */
export const PINNED_SKILL_IDS = ["workflow", "literature_search", "data_extraction", "image_gen", "ppt_generator"] as const;

/** 置顶入口：包含独立页面（工作流/文库/SAM/VASP）与工具（文生图） */
export interface PinnedEntry {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  /** 本应用内路径；无则仅展示，点击不跳转 */
  href?: string;
}

export const PINNED_ENTRIES: PinnedEntry[] = [
  { id: "workflow", name: "工作流", description: "编排与运行工作流", icon: Workflow, href: "/workspace/workflows" },
  { id: "image_gen", name: "文生图", description: "根据文本描述生成图片", icon: ImageIcon, href: "/workspace/toolbox/image_gen" },
];

const categoryLabels: Record<SkillCategory, string> = {
  molecular: "分子科学",
  literature: "文献研究",
  general: "通用技能",
};

export const SKILL_CATEGORIES: Array<{ id: SkillCategory | "all"; label: string }> = [
  { id: "all", label: "全部" },
  { id: "molecular", label: categoryLabels.molecular },
  { id: "literature", label: categoryLabels.literature },
  { id: "general", label: categoryLabels.general },
];

export function getSkillById(id: string): SkillConfig | undefined {
  return skills.find((s) => s.id === id);
}

export function getCategoryLabel(cat: SkillCategory): string {
  return categoryLabels[cat];
}
