"use client";

import { MarkdownContent } from "@/components/workspace/messages/markdown-content";
import { streamdownPlugins } from "@/core/streamdown/plugins";

/** 技能执行结果 Markdown 展示，与 agentic_workflow Markdown 用法一致 */
export function ToolMarkdown({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const content =
    typeof children === "string" ? children : String(children ?? "");
  if (!content) return null;
  return (
    <div className={className}>
      <MarkdownContent
        content={content}
        isLoading={false}
        rehypePlugins={streamdownPlugins.rehypePlugins}
        remarkPlugins={streamdownPlugins.remarkPlugins}
        className="text-sm"
      />
    </div>
  );
}
