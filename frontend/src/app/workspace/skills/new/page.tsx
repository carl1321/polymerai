"use client";

import { ArrowLeft, FolderUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useUploadSkillFolder } from "@/core/skills/hooks";

export default function NewSkillPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [pendingFolderName, setPendingFolderName] = useState<string>("");
  const [visibility, setVisibility] = useState<"user" | "org">("user");
  const [groupName, setGroupName] = useState("");
  const { mutateAsync: uploadSkillFolder, isPending: isUploading } =
    useUploadSkillFolder();

  const handleChooseFiles = (files: File[]) => {
    if (!files.length) return;
    setMessage(null);
    setPendingFiles(files);
    const firstRel =
      (files[0] as File & { webkitRelativePath?: string }).webkitRelativePath ||
      files[0]?.name ||
      "";
    const folder = firstRel.split("/")[0] || "";
    setPendingFolderName(folder);
  };

  const handleUpload = async () => {
    const files = pendingFiles;
    if (!files.length) {
      setMessage("请先选择技能文件夹。");
      return;
    }
    const hasSkillMd = files.some((f) => {
      const rel =
        (f as File & { webkitRelativePath?: string }).webkitRelativePath ||
        f.name;
      return /(^|\/)SKILL\.md$/i.test(rel);
    });
    if (!hasSkillMd) {
      setMessage("上传失败：目录根部缺少 SKILL.md。");
      return;
    }
    const result = await uploadSkillFolder({
      files,
      visibility,
      group_name: groupName.trim() || undefined,
    });
    setMessage(result.message);
    if (result.success) {
      setPendingFiles([]);
      setPendingFolderName("");
      setTimeout(() => {
        router.push("/workspace/toolbox");
      }, 600);
    }
  };

  return (
    <div className="flex h-full flex-col bg-[#F5F5F5] dark:bg-slate-900">
      <div className="shrink-0 px-6 py-4">
        <div className="overflow-hidden rounded-xl bg-gradient-to-br from-[#0f172a] via-[#1e3a5f] to-[#0f172a] p-8 text-white shadow-lg dark:from-slate-900 dark:via-blue-950/50 dark:to-slate-900">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xl font-bold">页面创建技能</h2>
            <Button
              variant="outline"
              size="sm"
              className="border-white/40 bg-transparent text-white hover:bg-white/10"
              onClick={() => router.push("/workspace/toolbox")}
            >
              <ArrowLeft className="h-4 w-4" />
              返回技能库
            </Button>
          </div>
          <p className="max-w-2xl text-sm text-white/90">
            上传一个技能文件夹（目录名即 skill 名），目录根部必须包含 SKILL.md。
          </p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 pb-6">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const files = Array.from(e.dataTransfer.files ?? []);
            handleChooseFiles(files);
          }}
          className={`rounded-xl border border-dashed bg-white p-8 dark:bg-slate-800 ${
            dragOver
              ? "border-[#1890FF] bg-[#E6F7FF]/50 dark:bg-blue-950/20"
              : "border-slate-300 dark:border-slate-600"
          }`}
        >
          <div className="mx-auto flex max-w-xl flex-col items-center gap-4 text-center">
            <div className="rounded-full bg-[#E6F7FF] p-3 dark:bg-blue-950/30">
              <FolderUp className="h-6 w-6 text-[#1890FF] dark:text-blue-400" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                拖拽技能文件夹到这里
              </h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                或点击下方按钮选择文件夹上传
              </p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              // @ts-expect-error webkitdirectory is supported by Chromium browsers.
              webkitdirectory=""
              directory=""
              multiple
              className="hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                handleChooseFiles(files);
                e.target.value = "";
              }}
            />
            <Button
              disabled={isUploading}
              onClick={() => fileInputRef.current?.click()}
              className="bg-[#1890FF] text-white hover:bg-[#40a9ff]"
            >
              选择技能文件夹
            </Button>
            <div className="w-full rounded-lg border border-slate-200 p-3 text-left dark:border-slate-700">
              <div className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                可见性与分类
              </div>
              <div className="grid grid-cols-1 gap-2">
                <select
                  value={visibility}
                  onChange={(e) =>
                    setVisibility(e.target.value as "user" | "org")
                  }
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm dark:border-slate-600 dark:bg-slate-800"
                >
                  <option value="user">私有（仅自己）</option>
                  <option value="org">公有（组织内）</option>
                </select>
                <input
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  placeholder="一级分类（可选，如 VASP计算）"
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm dark:border-slate-600 dark:bg-slate-800"
                />
              </div>
            </div>
            <div className="w-full rounded-lg border border-slate-200 p-3 text-left dark:border-slate-700">
              <div className="mb-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                已选文件夹
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400">
                {pendingFolderName
                  ? `${pendingFolderName}（${pendingFiles.length} 个文件）`
                  : "尚未选择"}
              </div>
            </div>
            <Button
              disabled={isUploading || pendingFiles.length === 0}
              onClick={() => void handleUpload()}
              className="bg-[#1890FF] text-white hover:bg-[#40a9ff]"
            >
              {isUploading ? "提交中..." : "提交创建"}
            </Button>
            {message && (
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {message}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
