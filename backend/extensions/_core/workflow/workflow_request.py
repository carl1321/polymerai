# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BreakCondition(BaseModel):
    """循环退出条件"""

    model_config = ConfigDict(populate_by_name=True)

    output_variable: str = Field(..., alias="outputVariable")  # 输出变量名（如"score"）
    operator: str  # 比较运算符（">=", "<=", ">", "<", "==", "!="）
    value: Any  # 比较值


class LoopVariableData(BaseModel):
    """循环变量数据"""

    model_config = ConfigDict(populate_by_name=True)

    label: str  # 变量标签
    var_type: str = Field(..., alias="varType")  # 变量类型：string, number, object, boolean, array_string, array_number, array_object, array_boolean
    value_type: str = Field(..., alias="valueType")  # 值类型：constant 或 variable
    value: Any | None = None  # 变量值


class WorkflowNodeData(BaseModel):
    """节点数据"""

    model_config = ConfigDict(populate_by_name=True)

    label: str
    node_name: str | None = Field(None, alias="nodeName")  # 节点名称（用于程序运行和记录）
    display_name: str | None = Field(None, alias="displayName")  # 显示名称（用于UI展示）
    # Start 节点
    start_inputs: list[dict[str, Any]] | None = Field(None, alias="startInputs")
    start_input_field: str | None = Field(None, alias="startInputField")
    start_files: dict[str, Any] | None = Field(None, alias="startFiles")

    @field_validator("start_inputs", mode="before")
    @classmethod
    def _coerce_start_inputs(cls, value: Any) -> Any:
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, dict):
            rows: list[dict[str, Any]] = []
            for key, item in value.items():
                if isinstance(item, dict):
                    rows.append({"key": key, **item})
                else:
                    rows.append({"key": key, "type": "string", "value": item})
            return rows
        return value

    @field_validator("start_files", mode="before")
    @classmethod
    def _coerce_start_files(cls, value: Any) -> Any:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {str(i): name for i, name in enumerate(value) if name}
        return value

    # LLM 节点
    llm_model: str | None = Field(None, alias="llmModel")
    llm_temperature: float | None = Field(None, alias="llmTemperature")
    llm_prompt: str | None = Field(None, alias="llmPrompt")
    llm_system_prompt: str | None = Field(None, alias="llmSystemPrompt")
    llm_resources: list[dict[str, Any]] | None = Field(None, alias="llmResources")  # 知识库资源
    llm_tools: list[str] | None = Field(None, alias="llmTools")  # 遗留字段，工作流 LLM 不再使用
    llm_skills: list[str] | None = Field(None, alias="llmSkills")  # 遗留多选，加载时迁移为 llmSkill
    llm_skill: str | None = Field(None, alias="llmSkill")  # 单选绑定的技能名
    # Tool 节点
    tool_name: str | None = Field(None, alias="toolName")
    tool_params: dict[str, Any] | None = Field(None, alias="toolParams")
    # API 节点
    api_url: str | None = Field(None, alias="apiUrl")
    api_method: str | None = Field(None, alias="apiMethod")
    api_headers: dict[str, str] | None = Field(None, alias="apiHeaders")
    api_body: str | None = Field(None, alias="apiBody")
    api_key: str | None = Field(None, alias="apiKey")  # API密钥
    # Condition 节点
    condition_expression: str | None = Field(None, alias="conditionExpression")
    # Variable 节点
    variable_name: str | None = Field(None, alias="variableName")
    variable_value: Any | None = Field(None, alias="variableValue")
    # 循环标记：标记节点属于哪个循环（通过 loopId）
    loop_id: str | None = Field(None, alias="loopId")  # 节点所属的循环ID
    # 输出格式：定义节点的输出格式（json 或 array）
    output_format: str | None = Field("json", alias="outputFormat")  # 输出格式，默认值为 json（{}）或 array（[{}]）
    # 输出字段定义：定义输出字段的结构
    output_fields: list[dict[str, Any]] | None = Field(None, alias="outputFields")  # 输出字段列表，每个字段包含 name 和 type
    # Loop 节点专用字段
    loop_count: int | None = Field(None, alias="loopCount")  # 最大循环次数
    break_conditions: list[BreakCondition] | None = Field(None, alias="breakConditions")  # 退出条件列表
    logical_operator: str | None = Field("and", alias="logicalOperator")  # 逻辑运算符："and" 或 "or"
    pending_items_variable_name: str | None = Field("pending_items", alias="pendingItemsVariableName")  # 待优化数据的循环变量名，默认为 "pending_items"
    start_node_id: str | None = Field(None, alias="startNodeId")  # 循环开始节点ID
    loop_variables: list[LoopVariableData] | None = Field(None, alias="loopVariables")  # 循环变量列表
    # Loop 节点尺寸和位置字段
    loop_width: int | None = Field(None, alias="loopWidth")  # Loop 节点宽度
    loop_height: int | None = Field(None, alias="loopHeight")  # Loop 节点高度
    relative_x: float | None = Field(None, alias="relativeX")  # 节点相对于循环体的 X 位置
    relative_y: float | None = Field(None, alias="relativeY")  # 节点相对于循环体的 Y 位置
    # 超时配置
    timeout_seconds: int | None = Field(None, alias="timeoutSeconds")  # 节点超时时间（秒）


class WorkflowNode(BaseModel):
    """工作流节点"""

    id: str
    type: str  # start, end, llm, tool, api, condition, variable, loop
    position: dict[str, float]  # {x, y}
    data: WorkflowNodeData


class WorkflowEdge(BaseModel):
    """工作流边/连接"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: str
    target: str
    source_handle: str | None = Field(None, alias="sourceHandle")
    target_handle: str | None = Field(None, alias="targetHandle")
    condition: str | None = None  # Condition 节点的条件分支
    # 参数映射已移除，改为在节点配置中使用 {{节点名.字段名}} 模板语法


def normalize_workflow_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize draft graph spec (startInputs list, etc.) before validation."""
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return spec
    for node in nodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data")
        if not isinstance(data, dict):
            continue
        si = data.get("startInputs")
        if isinstance(si, dict):
            rows: list[dict[str, Any]] = []
            for key, item in si.items():
                if isinstance(item, dict):
                    rows.append({"key": key, **item})
                else:
                    rows.append({"key": key, "type": "string", "value": item})
            data["startInputs"] = rows
    return spec


class WorkflowConfigRequest(BaseModel):
    """保存工作流配置请求"""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    name: str
    description: str | None = None
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    version: int | None = None


class WorkflowConfigResponse(BaseModel):
    """工作流配置响应"""

    model_config = ConfigDict(populate_by_name=True)  # 允许使用字段别名

    id: str
    name: str
    description: str | None = None
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    created_at: str | None = None
    updated_at: str | None = None
    version: int
    has_executed: bool | None = False  # 是否已执行
    execution_result: dict[str, Any] | None = None  # 执行结果（仅在 has_executed=True 时包含）


class WorkflowExecuteRequest(BaseModel):
    """执行工作流请求"""

    model_config = ConfigDict(populate_by_name=True)

    workflow_id: str = Field(..., alias="workflowId")
    inputs: dict[str, Any] | None = None
    files: list[str] | None = None
    thread_id: str | None = Field(None, alias="threadId")
    # 允许直接用草稿执行（避免“编辑后仍执行旧发布版本”）
    use_draft: bool = Field(False, alias="useDraft")
    # 可选：指定草稿ID；不提供则使用该工作流最新草稿
    draft_id: str | None = Field(None, alias="draftId")


class NodeExecuteRequest(BaseModel):
    """单独执行节点请求"""

    model_config = ConfigDict(populate_by_name=True)

    workflow_id: str | None = Field(None, alias="workflowId")
    node_id: str = Field(..., alias="nodeId")
    inputs: dict[str, Any] | None = None
    # 如果 workflow_id 为空，则使用 node_config 直接执行
    node_config: dict[str, Any] | None = Field(None, alias="nodeConfig")


class DirectNodeExecuteRequest(BaseModel):
    """直接执行节点请求（不需要工作流 ID）"""

    model_config = ConfigDict(populate_by_name=True)

    node_type: str = Field(..., alias="nodeType")
    node_data: dict[str, Any] = Field(..., alias="nodeData")
    inputs: dict[str, Any] | None = None


class WorkflowExecuteResponse(BaseModel):
    """工作流执行响应"""

    success: bool
    result: Any | None = None
    error: str | None = None
    execution_time: float | None = None
    node_results: dict[str, Any] | None = None


class NodeExecuteResponse(BaseModel):
    """节点执行响应"""

    success: bool
    node_id: str
    inputs: dict[str, Any] | None = None
    outputs: Any | None = None
    error: str | None = None
    execution_time: float | None = None


class ToolDefinition(BaseModel):
    """工具定义"""

    name: str
    description: str
    parameters: list[dict[str, Any]]


class WorkflowListResponse(BaseModel):
    """工作流列表响应"""

    workflows: list[dict[str, Any]]


class CreateWorkflowRequest(BaseModel):
    """创建工作流请求"""

    name: str
    description: str | None = None
    status: str = "draft"


class UpdateWorkflowRequest(BaseModel):
    """更新工作流请求"""

    name: str | None = None
    description: str | None = None
    status: str | None = None


class SaveDraftRequest(BaseModel):
    """保存草稿请求"""

    graph: dict[str, Any]  # 包含nodes和edges
    is_autosave: bool = False


class CreateReleaseRequest(BaseModel):
    """创建发布请求"""

    source_draft_id: str
    spec: dict[str, Any]  # 执行规范
    checksum: str
