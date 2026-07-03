// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { useCallback, useMemo, useState, useRef, useEffect } from "react";
import {
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  useNodesState,
  useEdgesState,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import type { Node, Edge, Connection, NodeTypes, EdgeChange } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button } from "~/components/ui/button";
import { ArrowLeft, Save, Play, Copy, Loader2 } from "lucide-react";
import { useDebouncedCallback } from "use-debounce";
import {
  LOOP_PADDING,
  normalizeNodesData,
  processNodesLayout,
  mapRunTaskStatusToExecutionStatus,
} from "../graph/workflow-graph-utils";
import { workflowNodeTypes } from "../graph/workflow-node-types";
import { NodeConfigPanel } from "./NodeConfigPanel";
import { EdgeConfigPanel } from "./EdgeConfigPanel";
import { NodePalette } from "./NodePalette";
import { nanoid } from "nanoid";
import { useRouter } from "next/navigation";
import {
  createRelease,
  createWorkflow,
  getDraft,
  getWorkflow,
  listWorkflows,
  saveDraft,
  createRun,
  getRun,
  getRunTasks,
  uploadRunInputs,
  patchRunInput,
} from "~/core/api/workflow";
import {
  WorkflowRunDialog,
  type StartInputFieldDef,
  type StartFilesDef,
} from "./WorkflowRunDialog";
import { sha256Hex } from "~/core/utils/crypto";
import { toast } from "sonner";
import {
  llmNodeIdsAffectedByEdgeChange,
  syncAutoLlmPromptsOnNodes,
} from "./utils/upstream";

const nodeTypes: NodeTypes = workflowNodeTypes;

interface WorkflowEditorProps {
  workflowId: string;
  workflowName: string;
  initialNodes: Node[];
  initialEdges: Edge[];
  onSave: (graph: { nodes: Node[]; edges: Edge[] }, isAutosave?: boolean) => Promise<any>;
  onBack: () => void;
}

function WorkflowEditorInner({
  workflowId,
  workflowName,
  initialNodes,
  initialEdges,
  onSave,
  onBack,
}: WorkflowEditorProps) {
  // 使用 useMemo 初始化节点状态，避免 useEffect 中的二次渲染导致的闪烁
  const initialProcessedNodes = useMemo(() => processNodesLayout(initialNodes), [initialNodes]);
  
  const [nodes, setNodes, onNodesChangeRaw] = useNodesState(initialProcessedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  
  // 保持 normalizeNodes 引用以兼容旧代码（虽然现在主要使用 normalizeNodesData）
  const normalizeNodes = useCallback((nodes: Node[]) => normalizeNodesData(nodes), []);

  // 包装 setNodes，确保所有节点更新都经过规范化
  const setNodesNormalized = useCallback(
    (updater: Node[] | ((nodes: Node[]) => Node[])) => {
      setNodes((nds) => {
        const newNodes = typeof updater === 'function' ? updater(nds) : updater;
        return normalizeNodesData(newNodes);
      });
    },
    [setNodes]
  );

  // 重置所有节点状态为初始 ready 状态（需在下方 useEffect 之前定义，避免 TDZ）
  const resetAllNodeStatuses = useCallback(() => {
    setNodesNormalized((nds) =>
      nds.map((node) => ({
        ...node,
        data: {
          ...node.data,
          executionStatus: "ready" as const,
          executionResult: undefined,
        },
      }))
    );
  }, [setNodesNormalized]);
  
  // 这里的 processNodes 仅仅是为了兼容可能的内部调用，实际逻辑已提取到 processNodesLayout
  const processNodes = useCallback((nodes: Node[]) => processNodesLayout(nodes), []);

  // 修改 onNodesChange 逻辑
  const onNodesChange = useCallback(
    (changes: any) => {
      onNodesChangeRaw(changes);
    },
    [onNodesChangeRaw]
  );

  // 处理拖拽结束，检测是否进入/离开循环
  const onNodeDragStop = useCallback((_: React.MouseEvent, node: Node) => {
      // 获取最新的节点列表（包括位置更新后的）
      // 注意：这里需要通过回调获取最新 state，或者依赖 nodes
      // 但 onNodeDragStop 的 node 参数是拖拽后的最新状态
      
      setNodes((nds) => {
          const currentNode = nds.find(n => n.id === node.id);
          if (!currentNode) return nds;
          
          // 如果节点是 loop，更新其尺寸数据（如果被resize）
          if (currentNode.type === "loop") return nds;
          
          // 查找所有循环节点
          const loopNodes = nds.filter(n => n.type === "loop");
          const nodeBounds = {
              x: node.position.x,
              y: node.position.y,
              width: node.width || 160,
              height: node.height || 60
          };
          
          // 如果节点已经有 parentId，position 是相对的，需要转绝对来检测是否拖出
          let absoluteX = node.position.x;
          let absoluteY = node.position.y;
          const currentParent = nds.find(n => n.id === node.parentId);
          
          if (currentParent) {
              absoluteX += currentParent.position.x;
              absoluteY += currentParent.position.y;
          }
          
          const centerX = absoluteX + nodeBounds.width / 2;
          const centerY = absoluteY + nodeBounds.height / 2;

          // 检测是否在某个 loop 内
          let targetLoop: Node | undefined;
          for (const loop of loopNodes) {
              const loopWRaw = loop.data?.loopWidth ?? loop.width;
              const loopHRaw = loop.data?.loopHeight ?? loop.height;
              const loopWNum = typeof loopWRaw === "number" ? loopWRaw : Number(loopWRaw);
              const loopHNum = typeof loopHRaw === "number" ? loopHRaw : Number(loopHRaw);
              const loopW = Number.isFinite(loopWNum) ? loopWNum : 600;
              const loopH = Number.isFinite(loopHNum) ? loopHNum : 400;
              
              if (
                  centerX >= loop.position.x + LOOP_PADDING.left &&
                  centerX <= loop.position.x + loopW - LOOP_PADDING.right &&
                  centerY >= loop.position.y + LOOP_PADDING.top &&
                  centerY <= loop.position.y + loopH - LOOP_PADDING.bottom
              ) {
                  targetLoop = loop;
                  break;
              }
          }
          
          // 状态更新
          if (targetLoop) {
              // 进入或仍在 Loop 中
              if (currentNode.parentId !== targetLoop.id) {
                  // 进入新 Loop
                  const relativeX = absoluteX - targetLoop.position.x;
                  const relativeY = absoluteY - targetLoop.position.y;
                  
                  return nds.map(n => n.id === node.id ? {
                      ...n,
                      parentId: targetLoop!.id,
                      position: { x: relativeX, y: relativeY },
                      extent: "parent",
                      data: { ...n.data, loopId: targetLoop!.id, loop_id: targetLoop!.id }
                  } : n);
              }
              // 仍在同一个 Loop 中，ReactFlow 已更新位置，不需要额外处理
              // 但可以强制更新 data.relativeX 等如果需要
              return nds; 
          } else {
              // 不在任何 Loop 中
              if (currentNode.parentId) {
                  // 刚刚拖出 Loop
                  return nds.map(n => n.id === node.id ? {
                      ...n,
                      parentId: undefined,
                      extent: undefined,
                      position: { x: absoluteX, y: absoluteY }, // 恢复绝对坐标
                      data: { 
                          ...n.data, 
                          loopId: undefined, 
                          loop_id: undefined, 
                          isLoopChild: undefined 
                       }
                  } : n);
              }
          }
          
          return nds;
      });
  }, [setNodes]);

  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [nodeTypeToAdd, setNodeTypeToAdd] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [runDialogSubmitting, setRunDialogSubmitting] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null); // 当前运行的 ID
  const [isReady, setIsReady] = useState(false); // 画布是否准备就绪
  const [isDuplicating, setIsDuplicating] = useState(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isUpdatingRef = useRef(false); // 防止无限递归的标志
  const router = useRouter();
  const { screenToFlowPosition, addNodes, fitView } = useReactFlow();

  const computeNextCopyName = useCallback(async (baseName: string): Promise<string> => {
    // 需求：名称后面加 1；若已存在则自动递增，避免重名带来的创建失败
    const trimmed = (baseName || "").trim() || "未命名工作流";
    let stem = trimmed;
    let startNum = 1;
    const m = trimmed.match(/^(.*?)(\d+)$/);
    if (m) {
      stem = m[1] || trimmed;
      startNum = (parseInt(m[2] ?? "0", 10) || 0) + 1;
    }

    const existing = new Set<string>();
    try {
      const res = await listWorkflows({ limit: 500 });
      for (const w of res.workflows || []) {
        if (w?.name) existing.add(String(w.name));
      }
    } catch {
      // 忽略：如果列表加载失败，就退化为最简单的 `${name}1`
    }

    // 优先满足“追加 1”的直觉：若原名不带数字，先尝试 `${name}1`
    if (!m) {
      const candidate = `${trimmed}1`;
      if (!existing.has(candidate)) return candidate;
      // 冲突则递增
      let i = 2;
      while (existing.has(`${trimmed}${i}`) && i < 1000) i += 1;
      return `${trimmed}${i}`;
    }

    // 原名本身带数字：使用递增后的数字
    let i = startNum;
    while (existing.has(`${stem}${i}`) && i < 1000) i += 1;
    return `${stem}${i}`;
  }, []);

  const handleDuplicateWorkflow = useCallback(async () => {
    if (isDuplicating) return;
    setIsDuplicating(true);
    try {
      // 1) 先确保当前画布的最新内容落盘（避免复制到旧版本）
      // 用 autosave=false，保证生成一个明确的草稿版本
      await onSave({ nodes, edges }, false);

      // 2) 读取当前工作流信息（用于复制 description/status）
      const wf = await getWorkflow(workflowId);
      const newName = await computeNextCopyName(wf?.name || workflowName || "未命名工作流");

      // 3) 创建新工作流
      const newWf = await createWorkflow({
        name: newName,
        description: wf?.description || "",
        status: wf?.status || "draft",
      });

      // 4) 复制最新草稿图（以最新 draft 为准，保证“一模一样”）
      // - 先取源工作流最新 draft（服务端存储的规范化 graph）
      // - 再保存到新工作流，生成其 draft
      const srcDraft = await getDraft(workflowId);
      await saveDraft(newWf.id, { graph: srcDraft.graph, is_autosave: false });

      toast.success(`已复制工作流：${newName}`);

      // 5) 自动打开新工作流编辑页
      router.push(`/workspace/workflows/${newWf.id}/editor`);
    } catch (e: any) {
      console.error("Duplicate workflow failed:", e);
      toast.error(e?.message || "复制工作流失败");
    } finally {
      setIsDuplicating(false);
    }
  }, [isDuplicating, onSave, nodes, edges, workflowId, workflowName, computeNextCopyName, router]);
  
  // 初始化画布视图：等待布局稳定后显示
  useEffect(() => {
    // 延迟一帧执行 fitView，确保 ReactFlow 内部节点已挂载
    const timer = requestAnimationFrame(() => {
      // 关闭动画，避免缩放过程带来的“先模糊后清晰”的视觉闪烁
      fitView({ padding: 0.2, duration: 0 });
      // 稍微延迟显示，让浏览器有时间渲染第一帧
      setTimeout(() => {
        setIsReady(true);
      }, 50);
    });
    
    return () => cancelAnimationFrame(timer);
  }, [fitView]);

  // deer-flow：状态恢复暂不依赖 run_status/status API；默认重置为 ready
  useEffect(() => {
    resetAllNodeStatuses();
  }, [workflowId, resetAllNodeStatuses]);

  // 自动保存（防抖）- 增加延迟时间以减少保存频率
  const debouncedSave = useDebouncedCallback(
    async (graph: { nodes: Node[]; edges: Edge[] }) => {
      try {
        setSaveStatus("saving");
        await onSave(graph, true);
        setSaveStatus("saved");
        setTimeout(() => setSaveStatus("idle"), 2000);
      } catch (error) {
        console.error("Auto-save failed:", error);
        setSaveStatus("error");
        setTimeout(() => setSaveStatus("idle"), 3000);
      }
    },
    2000 // 从 500ms 增加到 2000ms
  );

  // 当节点或边变化时，触发自动保存
  // 只在真正重要的变化时才保存（忽略位置变化）
  const prevGraphRef = useRef<{ 
    nodeIds: string[]; 
    edgeIds: string[];
    nodes: Node[]; // 保存之前的节点数据用于比较
  } | null>(null);
  
  useEffect(() => {
    // 计算当前图的结构（只关注节点和边的ID，忽略位置等）
    const currentGraph = {
      nodeIds: nodes.map(n => n.id).sort(),
      edgeIds: edges.map(e => `${e.source}-${e.target}`).sort(),
      nodes: nodes, // 保存当前节点数据
    };

    // 如果是首次渲染，只记录不保存
    if (!prevGraphRef.current) {
      prevGraphRef.current = currentGraph;
      return;
    }

    // 检查是否有结构性的变化（添加/删除节点或边）
    const hasStructuralChange = 
      JSON.stringify(currentGraph.nodeIds) !== JSON.stringify(prevGraphRef.current.nodeIds) ||
      JSON.stringify(currentGraph.edgeIds) !== JSON.stringify(prevGraphRef.current.edgeIds);

    // 检查是否有节点配置变化（通过比较节点的关键属性）
    const hasConfigChange = nodes.some((node) => {
      const prevNode = prevGraphRef.current?.nodes.find(n => n.id === node.id);
      if (!prevNode) return true; // 新节点
      
      // 比较关键配置属性（忽略位置、选择状态等）
      return (
        node.data?.taskName !== prevNode.data?.taskName ||
        node.data?.displayName !== prevNode.data?.displayName ||
        JSON.stringify(node.data?.llmPrompt) !== JSON.stringify(prevNode.data?.llmPrompt) ||
        JSON.stringify(node.data?.llmSystemPrompt) !== JSON.stringify(prevNode.data?.llmSystemPrompt) ||
        JSON.stringify(node.data?.llmModel) !== JSON.stringify(prevNode.data?.llmModel) ||
        JSON.stringify(node.data?.toolName) !== JSON.stringify(prevNode.data?.toolName) ||
        JSON.stringify(node.data?.toolParams) !== JSON.stringify(prevNode.data?.toolParams) ||
        JSON.stringify(node.data?.conditionExpression) !== JSON.stringify(prevNode.data?.conditionExpression) ||
        JSON.stringify(node.data?.startInputInfo) !== JSON.stringify(prevNode.data?.startInputInfo)
      );
    });

    // 只有在有结构性变化或配置变化时才保存
    if (hasStructuralChange || hasConfigChange) {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      
      // 增加延迟时间，从 1000ms 增加到 3000ms
      saveTimeoutRef.current = setTimeout(() => {
        debouncedSave({ nodes, edges });
        prevGraphRef.current = currentGraph;
      }, 3000);
    } else {
      // 即使没有重要变化，也更新引用（避免位置变化触发保存）
      prevGraphRef.current = currentGraph;
    }

    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [nodes, edges, debouncedSave]);

  // 手动保存
  const handleManualSave = useCallback(async () => {
    try {
      setSaveStatus("saving");
      await onSave({ nodes, edges }, false);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (error) {
      console.error("Save failed:", error);
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }, [nodes, edges, onSave]);

  // 更新节点执行状态
  const updateNodeExecutionStatus = useCallback((nodeId: string, status: "pending" | "ready" | "running" | "success" | "error" | "skipped" | "cancelled", resultData?: any) => {
    setNodesNormalized((nds) => {
      const nodeExists = nds.find(n => n.id === nodeId);
      if (!nodeExists) {
        console.warn(`节点 ${nodeId} 不存在于当前工作流中，无法更新状态`);
        return nds; // 如果节点不存在，返回原数组
      }
      
      return nds.map((node) => {
        if (node.id === nodeId) {
          const newData: any = {
            ...node.data,
            executionStatus: status,
          };
          
          if (resultData) {
            const existingResult: any = (node.data as any)?.executionResult ?? {};
            const newResult: any = {
              ...existingResult,
              ...resultData
            };
            
            // 如果是循环体内的节点，且payload包含iteration信息，需要合并iteration_outputs
            if (resultData.outputs?.iteration_outputs && Array.isArray(resultData.outputs.iteration_outputs)) {
              // 合并iteration_outputs数组
              const existingIterationOutputs = existingResult.outputs?.iteration_outputs || [];
              newResult.outputs = {
                ...existingResult.outputs,
                ...resultData.outputs,
                iteration_outputs: [...existingIterationOutputs, ...resultData.outputs.iteration_outputs]
              };
            } else if (resultData.outputs) {
              // 普通更新
              newResult.outputs = {
                ...existingResult.outputs,
                ...resultData.outputs
              };
            }
            
            newData.executionResult = newResult;
          }
          
          return {
            ...node,
            data: newData,
          };
        }
        return node;
      });
    });
    // 同时更新选中的节点
    setSelectedNode((prev) => {
      if (prev && prev.id === nodeId) {
        const newData: any = {
          ...prev.data,
          executionStatus: status,
        };
        
        if (resultData) {
          const existingResult: any = (prev.data as any)?.executionResult ?? {};
          const newResult: any = {
            ...existingResult,
            ...resultData
          };
          
          // 如果是循环体内的节点，且payload包含iteration信息，需要合并iteration_outputs
          if (resultData.outputs?.iteration_outputs && Array.isArray(resultData.outputs.iteration_outputs)) {
            // 合并iteration_outputs数组
            const existingIterationOutputs = existingResult.outputs?.iteration_outputs || [];
            newResult.outputs = {
              ...existingResult.outputs,
              ...resultData.outputs,
              iteration_outputs: [...existingIterationOutputs, ...resultData.outputs.iteration_outputs]
            };
          } else if (resultData.outputs) {
            // 普通更新
            newResult.outputs = {
              ...existingResult.outputs,
              ...resultData.outputs
            };
          }
          
          newData.executionResult = newResult;
        }
        
        return {
          ...prev,
          data: newData,
        };
      }
      return prev;
    });
  }, [setNodesNormalized]);

  const startNodeForRun = useMemo(
    () => nodes.find((n) => n.type === "start"),
    [nodes],
  );

  const executeWorkflowRun = useCallback(
    async (
      runInputs: Record<string, unknown>,
      opts?: { files?: File[]; fileFieldKeys?: string[] },
    ) => {
      try {
        setIsRunning(true);
        resetAllNodeStatuses();
        setSaveStatus("saving");
        const draft = await onSave({ nodes, edges }, false);
        setSaveStatus("saved");

        const spec = {
          name: workflowName || "未命名工作流",
          nodes: nodes.map((node) => ({
            id: node.id,
            type: node.type,
            position: node.position,
            data: { ...node.data, nodeName: node.data.taskName },
          })),
          edges: edges.map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            sourceHandle: edge.sourceHandle,
            targetHandle: edge.targetHandle,
            data: edge.data,
          })),
        };
        const checksum = await sha256Hex(JSON.stringify(spec));
        await createRelease(workflowId, { source_draft_id: draft.id, spec, checksum });

        const created = await createRun(workflowId, {}, { source: "ui" });
        const runId = created.run_id;
        if (created.work_root) {
          runInputs.work_root = created.work_root;
        }
        if (opts?.files && opts.files.length > 0) {
          const uploaded = await uploadRunInputs(workflowId, runId, opts.files);
          const pathFields =
            opts.fileFieldKeys && opts.fileFieldKeys.length > 0
              ? opts.fileFieldKeys
              : ["poscar_path"];
          uploaded.files.forEach((f, i) => {
            const key = pathFields[i] ?? pathFields[0] ?? "poscar_path";
            runInputs[key] = { file: f.relative };
          });
        }
        await patchRunInput(workflowId, runId, runInputs);
        setCurrentRunId(runId);
        toast.success("工作流已进入队列，开始执行");
        setRunDialogOpen(false);
        setRunDialogSubmitting(false);

        const terminalRunStatuses = new Set([
          "success",
          "failed",
          "canceled",
          "cancelled",
        ]);
        const terminalTaskStatuses = new Set([
          "success",
          "failed",
          "skipped",
          "canceled",
          "cancelled",
        ]);
        let polls = 0;
        const maxPolls = 7200;
        let suspendedNotified = false;

        while (true) {
          polls += 1;
          const run = await getRun(workflowId, runId);
          const tasks = await getRunTasks(workflowId, runId);
          const byNode: Record<string, any> = {};
          for (const t of tasks) byNode[String(t.node_id)] = t;

          setNodesNormalized((nds) =>
            nds.map((n) => {
              const t = byNode[n.id];
              if (!t) return n;
              const mapped = mapRunTaskStatusToExecutionStatus(String(t.status));
              return {
                ...n,
                data: {
                  ...n.data,
                  executionStatus: mapped,
                  executionResult: {
                    outputs: t.output,
                    error: t.error,
                    metrics: t.metrics,
                    startTime: t.started_at,
                    endTime: t.finished_at,
                  },
                },
              };
            }),
          );

          const runStatus = String(run?.status || "");
          const isSuspended =
            runStatus === "awaiting_external" ||
            tasks.some((t) => String(t.status) === "awaiting_external");
          const anyTaskFailed = tasks.some((t) => String(t.status) === "failed");
          const allTasksTerminal =
            tasks.length > 0 &&
            tasks.every((t) => terminalTaskStatuses.has(String(t.status)));
          const anyTaskActive = tasks.some((t) =>
            ["pending", "ready", "running", "awaiting_external"].includes(String(t.status)),
          );
          const runComplete =
            runStatus === "success" &&
            !anyTaskActive &&
            (tasks.length === 0 || allTasksTerminal);

          if (runComplete) {
            toast.success("工作流执行完成");
            break;
          }
          if (isSuspended || (runStatus === "success" && anyTaskActive)) {
            if (!suspendedNotified) {
              toast.info("工作流已挂起，等待外部任务执行完成…");
              suspendedNotified = true;
            }
          } else if (terminalRunStatuses.has(runStatus)) {
            toast.error("工作流执行失败/已取消");
            break;
          } else if (anyTaskFailed && (allTasksTerminal || polls >= 5)) {
            toast.error("工作流执行失败/已取消");
            break;
          }
          if (polls >= maxPolls) {
            toast.error("轮询超时，请在运行历史中查看状态");
            break;
          }
          await new Promise((r) => setTimeout(r, 1000));
        }
      } catch (error: any) {
        console.error("Run failed:", error);
        toast.error(error?.message || "运行工作流失败");
        setSaveStatus("error");
        setTimeout(() => setSaveStatus("idle"), 3000);
      } finally {
        setIsRunning(false);
        setRunDialogSubmitting(false);
        setRunDialogOpen(false);
      }
    },
    [nodes, edges, onSave, workflowId, workflowName, resetAllNodeStatuses, setNodesNormalized],
  );

  const handleRun = useCallback(() => {
    setRunDialogOpen(true);
  }, []);

  const handleRunDialogSubmit = useCallback(
    async (payload: {
      values: Record<string, string | number>;
      files: File[];
      fileFieldKeys: string[];
    }) => {
      setRunDialogSubmitting(true);
      const startData = (startNodeForRun?.data ?? {}) as Record<string, unknown>;
      const startInputInfo =
        typeof startData.startInputInfo === "string" ? startData.startInputInfo : "";
      const runInputs: Record<string, unknown> = { ...payload.values };
      if (startInputInfo.trim()) {
        runInputs.input = startInputInfo.trim();
      } else if (typeof payload.values.input === "string" && payload.values.input.trim()) {
        runInputs.input = payload.values.input.trim();
      }
      await executeWorkflowRun(runInputs, {
        files: payload.files,
        fileFieldKeys: payload.fileFieldKeys,
      });
    },
    [startNodeForRun, executeWorkflowRun],
  );

  const syncLlmPromptsAfterEdgeChange = useCallback(
    (anchorTargets: Iterable<string>, nextEdges: Edge[]) => {
      setNodesNormalized((nds) =>
        syncAutoLlmPromptsOnNodes(
          nds,
          nextEdges,
          llmNodeIdsAffectedByEdgeChange(anchorTargets, nds, nextEdges),
        ),
      );
    },
    [setNodesNormalized],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const removedTargets: string[] = [];
      for (const c of changes) {
        if (c.type === "remove") {
          const edge = edges.find((e) => e.id === c.id);
          if (edge?.target) removedTargets.push(edge.target);
        }
      }
      setEdges((eds) => {
        const nextEds = applyEdgeChanges(changes, eds);
        if (removedTargets.length > 0) {
          syncLlmPromptsAfterEdgeChange(removedTargets, nextEds);
        }
        return nextEds;
      });
    },
    [edges, setEdges, syncLlmPromptsAfterEdgeChange],
  );

  const onConnect = useCallback(
    (params: Connection) => {
      if (!params.target) return;
      setEdges((eds) => {
        const nextEds = addEdge(params, eds);
        syncLlmPromptsAfterEdgeChange([params.target!], nextEds);
        return nextEds;
      });
    },
    [setEdges, syncLlmPromptsAfterEdgeChange],
  );

  // 选择节点
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
    setSelectedEdge(null);
  }, []);

  // 选择边
  const onEdgeClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }, []);

  // 更新节点数据
  const handleNodeUpdate = useCallback(
    (nodeId: string, data: any) => {
      setNodesNormalized((nds) =>
        nds.map((node) => {
          if (node.id === nodeId) {
            const updatedData = {
              ...node.data,
              ...data,
            };
            // 确保 nodeName 和 displayName 始终是字符串
            if (updatedData.nodeName !== undefined && updatedData.nodeName !== null) {
              updatedData.nodeName = String(updatedData.nodeName);
            }
            if (updatedData.displayName !== undefined && updatedData.displayName !== null) {
              updatedData.displayName = String(updatedData.displayName);
            }
            // 确保 label 也是字符串（如果存在）
            if (updatedData.label !== undefined && updatedData.label !== null) {
              updatedData.label = String(updatedData.label);
            }
            return { ...node, data: updatedData };
          }
          return node;
        })
      );
      setSelectedNode((prev) => {
        if (prev && prev.id === nodeId) {
          const updatedData = {
            ...prev.data,
            ...data,
          };
          // 确保 nodeName 和 displayName 始终是字符串
          if (updatedData.taskName !== undefined && updatedData.taskName !== null) {
            updatedData.taskName = String(updatedData.taskName);
          }
          if (updatedData.displayName !== undefined && updatedData.displayName !== null) {
            updatedData.displayName = String(updatedData.displayName);
          }
          if (updatedData.label !== undefined && updatedData.label !== null) {
            updatedData.label = String(updatedData.label);
          }
          return { ...prev, data: updatedData };
        }
        return prev;
      });
    },
    [setNodes]
  );

  // 更新边数据
  const handleEdgeUpdate = useCallback(
    (edgeId: string, data: any) => {
      setEdges((eds) =>
        eds.map((edge) => (edge.id === edgeId ? { ...edge, data } : edge))
      );
      setSelectedEdge((prev) => (prev && prev.id === edgeId ? { ...prev, data } : prev));
    },
    [setEdges]
  );

  // 删除节点和边
  const onNodesDelete = useCallback((deleted: Node[]) => {
    const deletedLoopIds = deleted.filter((n) => n.type === "loop").map((n) => n.id);

    setEdges((eds) => {
      const nextEds = eds.filter(
        (edge) =>
          !deleted.find((d) => d.id === edge.source || d.id === edge.target),
      );
      setNodesNormalized((nds) => {
        let nextNds: Node[];
        if (deletedLoopIds.length > 0) {
          const childNodeIds = new Set<string>();
          deletedLoopIds.forEach((loopId) => {
            nds.forEach((node) => {
              const nodeLoopId = node.data?.loopId || node.data?.loop_id;
              if (nodeLoopId === loopId) {
                childNodeIds.add(node.id);
              }
            });
          });
          const allDeletedIds = new Set([
            ...deleted.map((n) => n.id),
            ...Array.from(childNodeIds),
          ]);
          nextNds = nds.filter((node) => !allDeletedIds.has(node.id));
        } else {
          nextNds = nds.filter((node) => !deleted.find((d) => d.id === node.id));
        }
        const llmIds = nextNds.filter((n) => n.type === "llm").map((n) => n.id);
        return syncAutoLlmPromptsOnNodes(nextNds, nextEds, llmIds);
      });
      return nextEds;
    });
    // 清除选中状态
    if (selectedNode && deleted.find((d) => d.id === selectedNode.id)) {
      setSelectedNode(null);
    }
  }, [setNodesNormalized, setEdges, selectedNode]);

  // 添加键盘事件监听器处理 Delete 键和 Backspace 键
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // 检查是否在输入框、文本域等可编辑元素中
      const target = event.target as HTMLElement;
      const isEditable = 
        target.tagName === "INPUT" || 
        target.tagName === "TEXTAREA" || 
        target.isContentEditable;
      
      // 如果正在编辑文本，不处理删除操作
      if (isEditable) {
        return;
      }
      
      // 检查是否按下了 Delete 键或 Backspace 键
      if (event.key === "Delete" || event.key === "Backspace") {
        // 检查是否有选中的节点或边
        if (selectedNode) {
          event.preventDefault();
          event.stopPropagation();
          setNodesNormalized((nds) => nds.filter((node) => node.id !== selectedNode.id));
          setEdges((eds) => {
            const nextEds = eds.filter(
              (edge) =>
                edge.source !== selectedNode.id && edge.target !== selectedNode.id,
            );
            setNodesNormalized((nds) => {
              const nextNds = nds.filter((node) => node.id !== selectedNode.id);
              const llmIds = nextNds.filter((n) => n.type === "llm").map((n) => n.id);
              return syncAutoLlmPromptsOnNodes(nextNds, nextEds, llmIds);
            });
            return nextEds;
          });
          setSelectedNode(null);
        } else if (selectedEdge) {
          event.preventDefault();
          event.stopPropagation();
          setEdges((eds) => {
            const removed = eds.find((edge) => edge.id === selectedEdge.id);
            const nextEds = eds.filter((edge) => edge.id !== selectedEdge.id);
            if (removed?.target) {
              syncLlmPromptsAfterEdgeChange([removed.target], nextEds);
            }
            return nextEds;
          });
          setSelectedEdge(null);
        }
      }
    };
    
    // 使用全局 window 监听，确保能捕获到键盘事件
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [selectedNode, selectedEdge, setNodesNormalized, setEdges, syncLlmPromptsAfterEdgeChange]);

  // 在画布上添加节点
  const onPaneClick = useCallback(
    (event: React.MouseEvent) => {
      if (nodeTypeToAdd) {
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });
        
      // 检查新节点是否在某个循环节点内
      let parentId: string | undefined;
      let finalPosition = position;
      let extent: 'parent' | undefined;
      let loopId: string | undefined;

      const loopNodes = nodes.filter(n => n.type === "loop");
      for (const loopNode of loopNodes) {
        const loopWidthRaw = loopNode.data?.loopWidth ?? loopNode.width;
        const loopHeightRaw = loopNode.data?.loopHeight ?? loopNode.height;
        const loopWidthNum =
          typeof loopWidthRaw === "number" ? loopWidthRaw : Number(loopWidthRaw);
        const loopHeightNum =
          typeof loopHeightRaw === "number" ? loopHeightRaw : Number(loopHeightRaw);
        const loopWidth = Number.isFinite(loopWidthNum) ? loopWidthNum : 600;
        const loopHeight = Number.isFinite(loopHeightNum) ? loopHeightNum : 400;
        
        if (
            position.x >= loopNode.position.x + LOOP_PADDING.left &&
            position.x <= loopNode.position.x + loopWidth - LOOP_PADDING.right &&
            position.y >= loopNode.position.y + LOOP_PADDING.top &&
            position.y <= loopNode.position.y + loopHeight - LOOP_PADDING.bottom
        ) {
            parentId = loopNode.id;
            loopId = loopNode.id;
            extent = 'parent';
            
            // 计算相对位置
            finalPosition = {
                x: Math.max(0, position.x - loopNode.position.x - LOOP_PADDING.left),
                y: Math.max(0, position.y - loopNode.position.y - LOOP_PADDING.top)
            };
            break;
        }
      }

      const nodeName = generateNodeName(nodeTypeToAdd, nodes);
      const newNode: Node = {
        id: nanoid(),
        type: nodeTypeToAdd,
        position: finalPosition,
        parentId,
        extent,
        data: { 
          taskName: nodeName,
          displayName:
            nodeName === "start"
              ? "开始"
              : nodeName === "end"
                ? "结束"
                : nodeTypeToAdd === "tool"
                  ? "工具"
                  : nodeName,
          label:
            nodeName === "start"
              ? "开始"
              : nodeName === "end"
                ? "结束"
                : nodeTypeToAdd === "tool"
                  ? "工具"
                  : nodeName,
          ...(nodeTypeToAdd === "loop" ? { loopCount: 3, loop_count: 3 } : {}),
          loopId,
          loop_id: loopId,
          isLoopChild: !!loopId,
        },
        style: loopId ? { zIndex: 15, pointerEvents: "auto" } : undefined,
      };
        
      addNodes(normalizeNodes([newNode]));
      setNodeTypeToAdd(null);

      }
    },
    [nodeTypeToAdd, screenToFlowPosition, addNodes]
  );

  // 处理拖放
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData("application/reactflow");
      if (!type) {
        return;
      }

      // 检查开始和结束节点的唯一性
      if (type === "start") {
        const hasStart = nodes.some((n) => n.type === "start");
        if (hasStart) {
          return;
        }
      }
      if (type === "end") {
        const hasEnd = nodes.some((n) => n.type === "end");
        if (hasEnd) {
          return;
        }
      }

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      // 检查新节点是否在某个循环节点内
      let parentId: string | undefined;
      let finalPosition = position;
      let extent: 'parent' | undefined;
      let loopId: string | undefined;

      const loopNodes = nodes.filter(n => n.type === "loop");
      for (const loopNode of loopNodes) {
        const loopWidthRaw = loopNode.data?.loopWidth ?? loopNode.width;
        const loopHeightRaw = loopNode.data?.loopHeight ?? loopNode.height;
        const loopWidthNum =
          typeof loopWidthRaw === "number" ? loopWidthRaw : Number(loopWidthRaw);
        const loopHeightNum =
          typeof loopHeightRaw === "number" ? loopHeightRaw : Number(loopHeightRaw);
        const loopWidth = Number.isFinite(loopWidthNum) ? loopWidthNum : 600;
        const loopHeight = Number.isFinite(loopHeightNum) ? loopHeightNum : 400;
        
        if (
            position.x >= loopNode.position.x + LOOP_PADDING.left &&
            position.x <= loopNode.position.x + loopWidth - LOOP_PADDING.right &&
            position.y >= loopNode.position.y + LOOP_PADDING.top &&
            position.y <= loopNode.position.y + loopHeight - LOOP_PADDING.bottom
        ) {
            parentId = loopNode.id;
            loopId = loopNode.id;
            extent = 'parent';
            
            // 计算相对位置
            finalPosition = {
                x: Math.max(0, position.x - loopNode.position.x - LOOP_PADDING.left),
                y: Math.max(0, position.y - loopNode.position.y - LOOP_PADDING.top)
            };
            break;
        }
      }

      const nodeName = generateNodeName(type, nodes);
      const newNode: Node = {
        id: nanoid(),
        type,
        position: finalPosition,
        parentId,
        extent,
        data: { 
          taskName: nodeName,
          displayName:
            nodeName === "start"
              ? "开始"
              : nodeName === "end"
                ? "结束"
                : type === "tool"
                  ? "工具"
                  : nodeName,
          label:
            nodeName === "start"
              ? "开始"
              : nodeName === "end"
                ? "结束"
                : type === "tool"
                  ? "工具"
                  : nodeName,
          ...(type === "loop" ? { loopCount: 3, loop_count: 3 } : {}),
          loopId,
          loop_id: loopId,
          isLoopChild: !!loopId,
        },
        style: loopId ? { zIndex: 15, pointerEvents: "auto" } : undefined,
      };

      addNodes(normalizeNodes([newNode]));

    },
    [screenToFlowPosition, addNodes, nodes, normalizeNodes]
  );

  // 生成节点名称（用于程序运行和记录）
  const generateNodeName = useCallback((type: string, existingNodes: Node[]): string => {
    // 开始和结束节点固定名称
    if (type === "start") return "start";
    if (type === "end") return "end";
    
    // 获取节点类型的中文名称映射
    if (type === "tool") {
      const count = existingNodes.filter((n) => n.type === "tool").length;
      return count === 0 ? "tool" : `tool${count}`;
    }

    const typeLabels: Record<string, string> = {
      llm: "LLM",
      condition: "条件",
      loop: "loop",
    };

    const baseName = typeLabels[type] || type;
    
    // 统计同类型节点的数量
    const sameTypeNodes = existingNodes.filter(n => n.type === type);
    const count = sameTypeNodes.length;
    
    // 第一个节点不加数字，后续加数字
    return count === 0 ? baseName : `${baseName}${count}`;
  }, []);

  // 获取节点显示名称（用于界面显示）
  const getNodeDisplayName = (node: Node): string => {
    const d: any = node.data;
    const v =
      (typeof d?.displayName === "string" && d.displayName) ||
      (typeof d?.label === "string" && d.label) ||
      (typeof d?.nodeName === "string" && d.nodeName) ||
      "";
    return v || "未命名";
  };

  const saveStatusText = useMemo(() => {
    switch (saveStatus) {
      case "saving":
        return "保存中...";
      case "saved":
        return "已保存";
      case "error":
        return "保存失败";
      default:
        return "";
    }
  }, [saveStatus]);

  const startDialogInputs = useMemo((): StartInputFieldDef[] => {
    const raw = (startNodeForRun?.data as Record<string, unknown> | undefined)?.startInputs;
    return Array.isArray(raw) ? (raw as StartInputFieldDef[]) : [];
  }, [startNodeForRun]);

  const startDialogFiles = useMemo((): StartFilesDef | undefined => {
    const raw = (startNodeForRun?.data as Record<string, unknown> | undefined)?.startFiles;
    if (raw === null || raw === false) return undefined;
    if (raw && typeof raw === "object") return raw as StartFilesDef;
    return { accept: ".vasp,.cif,.poscar,.POSCAR,.CONTCAR", maxCount: 5 };
  }, [startNodeForRun]);

  const startAllowFileUpload = useMemo(() => {
    const raw = (startNodeForRun?.data as Record<string, unknown> | undefined)?.startFiles;
    return raw !== null && raw !== false;
  }, [startNodeForRun]);

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <WorkflowRunDialog
        open={runDialogOpen}
        onOpenChange={setRunDialogOpen}
        startInputInfo={
          typeof (startNodeForRun?.data as Record<string, unknown>)?.startInputInfo === "string"
            ? ((startNodeForRun?.data as Record<string, unknown>).startInputInfo as string)
            : undefined
        }
        startInputs={startDialogInputs}
        startFiles={startDialogFiles}
        allowFileUpload={startAllowFileUpload}
        submitting={runDialogSubmitting}
        onSubmit={handleRunDialogSubmit}
      />
      {/* 顶部工具栏 */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex flex-col">
            <h1 className="text-lg font-semibold text-foreground">{workflowName}</h1>
            <p className="text-xs text-muted-foreground">工作流编辑器</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-sm text-muted-foreground">{saveStatusText}</div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDuplicateWorkflow}
            disabled={isDuplicating || isRunning || saveStatus === "saving"}
          >
            {isDuplicating ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                复制中...
              </>
            ) : (
              <>
                <Copy className="h-4 w-4 mr-2" />
                复制
              </>
            )}
          </Button>
          <Button onClick={handleManualSave} size="sm" disabled={saveStatus === "saving"}>
            <Save className="h-4 w-4 mr-2" />
            保存
          </Button>
          <Button 
            onClick={handleRun} 
            size="sm" 
            variant="default"
            className="bg-blue-500 hover:bg-blue-600"
            disabled={isRunning || saveStatus === "saving"}
          >
            <Play className="h-4 w-4 mr-2" />
            {isRunning ? "执行中..." : "执行"}
          </Button>
        </div>
      </div>

      {/* 主内容区：min-h-0 使 flex 子项可收缩，避免撑出页面产生底部滚动条 */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {/* 节点库 */}
        <NodePalette onNodeTypeSelect={setNodeTypeToAdd} />

        {/* 画布 */}
        <div 
          className="relative flex-1 bg-app transition-opacity duration-300 ease-in-out"
          style={{ opacity: isReady ? 1 : 0 }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onNodesDelete={onNodesDelete}
            onPaneClick={onPaneClick}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeDragStop={onNodeDragStop}
            nodeTypes={nodeTypes}
            deleteKeyCode={["Delete", "Backspace"]} // 启用 Delete 和 Backspace 删除节点和边
            attributionPosition="bottom-left"
          >

            <Controls />
            <MiniMap />
            <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
          </ReactFlow>
        </div>

        {/* 配置面板：足够宽以完整显示中文，高度占满并支持内部滚动 */}
        {(selectedNode || selectedEdge) && (
          <div className="w-[480px] min-w-[480px] flex-shrink-0 border-l border-border bg-card flex flex-col min-h-0">
            {selectedNode && (
              <NodeConfigPanel
                node={selectedNode}
                nodes={nodes}
                edges={edges}
                onUpdate={handleNodeUpdate}
                onClose={() => setSelectedNode(null)}
                workflowId={workflowId}
                currentRunId={currentRunId}
              />
            )}
            {selectedEdge && (
              <EdgeConfigPanel
                edge={selectedEdge}
                onUpdate={handleEdgeUpdate}
                onClose={() => setSelectedEdge(null)}
              />
            )}
          </div>
        )}
      </div>

    </div>
  );
}
export function WorkflowEditor(props: WorkflowEditorProps) {
  return (
    <ReactFlowProvider>
      <WorkflowEditorInner {...props} />
    </ReactFlowProvider>
  );
}


