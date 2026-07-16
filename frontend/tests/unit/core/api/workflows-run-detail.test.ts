import { describe, expect, it } from "vitest";

import { shouldPollRunProgress } from "@/components/workflow/runs/run-display-utils";
import { mapRunTasksToNodeExecutions } from "@/core/api/workflows";
import type { WorkflowRunDetail } from "@/core/api/workflows";

describe("mapRunTasksToNodeExecutions", () => {
  it("enriches from node_index and uses resolved_inputs when input empty", () => {
    const nodes = mapRunTasksToNodeExecutions(
      [
        {
          id: "t1",
          node_id: "n1",
          status: "success",
          started_at: "2025-01-01T00:00:00Z",
          finished_at: "2025-01-01T00:00:10Z",
          input: {},
          output: { resolved_inputs: { prompt: "hi" } },
          run_seq: 2,
        },
        {
          id: "t0",
          node_id: "n0",
          status: "awaiting_external",
          run_seq: 1,
        },
      ],
      {
        n1: { node_name: "Relax", type: "llm", skill: "vasp-relax" },
      },
    );
    expect(nodes).toHaveLength(2);
    expect(nodes[0].node_id).toBe("n0");
    expect(nodes[1].node_name).toBe("Relax");
    expect(nodes[1].input).toEqual({ prompt: "hi" });
    expect(nodes[1].duration_ms).toBe(10_000);
  });
});

describe("shouldPollRunProgress", () => {
  const base: WorkflowRunDetail = {
    run: { status: "success" },
    nodes: [],
    async_tasks: [],
  };

  it("polls when run is active", () => {
    expect(
      shouldPollRunProgress({ ...base, run: { status: "awaiting_external" } }),
    ).toBe(true);
    expect(shouldPollRunProgress({ ...base, run: { status: "running" } })).toBe(
      true,
    );
  });

  it("polls when async tasks still active", () => {
    expect(
      shouldPollRunProgress({
        ...base,
        async_tasks: [{ id: "1", task_name: "x", status: "running" }],
      }),
    ).toBe(true);
  });

  it("stops when run and async are terminal", () => {
    expect(
      shouldPollRunProgress({
        ...base,
        run: { status: "success" },
        nodes: [{ node_id: "n1", status: "success" }],
        async_tasks: [{ id: "1", task_name: "x", status: "succeeded" }],
      }),
    ).toBe(false);
  });

  it("keeps polling when run is success but a node is still awaiting_external", () => {
    expect(
      shouldPollRunProgress({
        ...base,
        run: { status: "success" },
        nodes: [
          { node_id: "n1", status: "success" },
          { node_id: "n2", status: "awaiting_external" },
        ],
      }),
    ).toBe(true);
  });
});
