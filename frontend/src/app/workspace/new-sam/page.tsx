// @ts-nocheck
"use client";

// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";

import { SamDesignUnifiedPage } from "@/app/workspace/new-sam/components/SamDesignUnifiedPage";
import { Step1DefineObjective } from "@/app/workspace/new-sam/components/Step1DefineObjective";
import type {
  DesignState,
  DesignObjective,
  Constraint,
} from "@/app/workspace/new-sam/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * 从 localStorage 加载设计状态
 */
function loadDesignState(): Partial<DesignState> {
  if (typeof window === "undefined") return {};
  try {
    const saved = localStorage.getItem("new-sam-design-state");
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (error) {
    console.error("Failed to load design state:", error);
  }
  return {};
}

/**
 * 保存设计状态到 localStorage
 */
function saveDesignState(state: Partial<DesignState>) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem("new-sam-design-state", JSON.stringify(state));
  } catch (error) {
    console.error("Failed to save design state:", error);
  }
}

/**
 * 新SAM分子设计主页面（统一单页布局）
 */
export default function NewSAMDesignPage() {
  const router = useRouter();

  // 使用useState和useEffect来避免hydration错误
  const [isClient, setIsClient] = useState(false);
  const [objective, setObjective] = useState<DesignObjective>({ text: "" });
  const [constraints, setConstraints] = useState<Constraint[]>([]);
  const [editObjectiveDialogOpen, setEditObjectiveDialogOpen] = useState(false);

  // 在客户端加载保存的状态
  useEffect(() => {
    setIsClient(true);
    const savedState = loadDesignState();

    if (savedState.objective) {
      setObjective(savedState.objective);
    }
    if (savedState.constraints && savedState.constraints.length > 0) {
      setConstraints(savedState.constraints);
    } else {
      // 只在客户端生成默认约束，使用固定ID避免hydration错误
      const defaultConstraints: Constraint[] = [
        {
          id: "constraint-1-default",
          name: "表面锚定强度",
          type: "surface_anchoring",
          valueType: "select",
          value: "High",
          enabled: true,
          options: ["High", "Medium", "Low"],
        },
        {
          id: "constraint-2-default",
          name: "能级匹配",
          type: "energy_level",
          valueType: "range",
          value: { min: -0.2, max: 0.2 },
          enabled: true,
          unit: "eV",
        },
        {
          id: "constraint-3-default",
          name: "膜致密度和稳定性",
          type: "packing_density",
          valueType: "select",
          value: "High",
          enabled: true,
          options: ["High", "Medium", "Low"],
        },
      ];
      setConstraints(defaultConstraints);
    }
  }, []);

  // 保存状态到 localStorage
  useEffect(() => {
    if (!isClient) return; // 只在客户端保存

    const state: Partial<DesignState> = {
      objective,
      constraints,
    };
    saveDesignState(state);
  }, [objective, constraints, isClient]);

  if (!isClient) {
    return null; // 避免 hydration 错误
  }

  const handleBackToToolbox = () => {
    router.push("/workspace/agents");
  };

  return (
    <>
      <div className="flex h-screen flex-col bg-slate-50 dark:bg-slate-950">
        <div className="flex flex-shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-6 py-4 dark:border-slate-700 dark:bg-slate-900">
          <Button
            variant="ghost"
            size="icon"
            onClick={handleBackToToolbox}
            className="h-8 w-8"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <span className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            SAM 分子设计
          </span>
        </div>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <SamDesignUnifiedPage
            objective={objective}
            onObjectiveChange={setObjective}
            constraints={constraints}
            onConstraintsChange={setConstraints}
            onEditObjective={() => setEditObjectiveDialogOpen(true)}
          />
        </div>
      </div>

      {/* 编辑研究目标对话框 */}
      <Dialog
        open={editObjectiveDialogOpen}
        onOpenChange={setEditObjectiveDialogOpen}
      >
        <DialogContent className="max-h-[90vh] w-[85vw] !max-w-[85vw] overflow-y-auto p-6">
          <DialogHeader className="pb-4">
            <DialogTitle>编辑研究目标</DialogTitle>
          </DialogHeader>
          <div className="px-2">
            <Step1DefineObjective
              objective={objective}
              onObjectiveChange={(newObjective) => {
                setObjective(newObjective);
                setEditObjectiveDialogOpen(false);
              }}
              constraints={constraints}
              onConstraintsChange={setConstraints}
              onNext={() => setEditObjectiveDialogOpen(false)}
              showValidation={false}
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
