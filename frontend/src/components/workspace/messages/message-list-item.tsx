import type { Message } from "@langchain/langgraph-sdk";
import {
  FileIcon,
  Loader2Icon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
  type ImgHTMLAttributes,
} from "react";
import rehypeKatex from "rehype-katex";

import { Loader } from "@/components/ai-elements/loader";
import {
  Message as AIElementMessage,
  MessageContent as AIElementMessageContent,
  MessageResponse as AIElementMessageResponse,
  MessageToolbar,
} from "@/components/ai-elements/message";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { Task, TaskTrigger } from "@/components/ai-elements/task";
import { Badge } from "@/components/ui/badge";
import {
  deleteFeedback,
  upsertFeedback,
  type FeedbackData,
} from "@/core/api/feedback";
import { resolveArtifactURL } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import {
  extractContentFromMessage,
  extractPresentFilesFromMessage,
  extractReasoningContentFromMessage,
  parseUploadedFiles,
  stripUploadedFilesTag,
  type FileInMessage,
} from "@/core/messages/utils";
import { useRehypeSplitWordsIntoSpans } from "@/core/rehype";
import { humanMessagePlugins } from "@/core/streamdown";
import { getToken } from "@/core/auth/token";
import { cn } from "@/lib/utils";

import { CopyButton } from "../copy-button";

import { MarkdownContent } from "./markdown-content";

function FeedbackButtons({
  threadId,
  runId,
  initialFeedback,
}: {
  threadId: string;
  runId: string;
  initialFeedback: FeedbackData | null;
}) {
  const [feedback, setFeedback] = useState<FeedbackData | null>(
    initialFeedback,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleClick = useCallback(
    async (rating: number) => {
      if (isSubmitting) return;
      setIsSubmitting(true);
      try {
        if (feedback?.rating === rating) {
          await deleteFeedback(threadId, runId);
          setFeedback(null);
        } else {
          const result = await upsertFeedback(threadId, runId, rating);
          setFeedback(result);
        }
      } catch {
        // Revert on error — feedback state unchanged on catch
      } finally {
        setIsSubmitting(false);
      }
    },
    [threadId, runId, feedback, isSubmitting],
  );

  return (
    <div className="flex gap-1">
      <button
        type="button"
        className={cn(
          "text-muted-foreground hover:text-foreground rounded-md p-1 transition-colors",
          feedback?.rating === 1 && "text-foreground",
        )}
        onClick={() => handleClick(1)}
        disabled={isSubmitting}
      >
        <ThumbsUpIcon
          className={cn("size-4", feedback?.rating === 1 && "fill-current")}
        />
      </button>
      <button
        type="button"
        className={cn(
          "text-muted-foreground hover:text-foreground rounded-md p-1 transition-colors",
          feedback?.rating === -1 && "text-foreground",
        )}
        onClick={() => handleClick(-1)}
        disabled={isSubmitting}
      >
        <ThumbsDownIcon
          className={cn("size-4", feedback?.rating === -1 && "fill-current")}
        />
      </button>
    </div>
  );
}

export function MessageListItem({
  className,
  message,
  isLoading,
  feedback,
  runId,
  answerFinishedAt,
  answerDurationMs,
  threadId,
  showCopyButton = true,
}: {
  className?: string;
  message: Message;
  isLoading?: boolean;
  threadId: string;
  feedback?: FeedbackData | null;
  runId?: string;
  answerFinishedAt?: string;
  answerDurationMs?: number;
  showCopyButton?: boolean;
}) {
  const isHuman = message.type === "human";
  return (
    <AIElementMessage
      className={cn("group/conversation-message relative w-full", className)}
      from={isHuman ? "user" : "assistant"}
    >
      <MessageContent
        className={isHuman ? "w-fit" : "w-full"}
        message={message}
        isLoading={isLoading}
        threadId={threadId}
        answerFinishedAt={answerFinishedAt}
        answerDurationMs={answerDurationMs}
      />
      {!isLoading && showCopyButton && (
        <MessageToolbar
          className={cn(
            isHuman
              ? "absolute right-0 -bottom-9 left-0 justify-end"
              : "absolute right-0 bottom-0 left-0",
            "z-20 opacity-0 transition-opacity delay-200 duration-300 group-hover/conversation-message:opacity-100",
          )}
        >
          <div className="pointer-events-auto flex gap-1">
            <CopyButton
              clipboardData={
                extractContentFromMessage(message) ??
                extractReasoningContentFromMessage(message) ??
                ""
              }
            />
            {feedback !== undefined && runId && threadId && (
              <FeedbackButtons
                threadId={threadId}
                runId={runId}
                initialFeedback={feedback}
              />
            )}
          </div>
        </MessageToolbar>
      )}
    </AIElementMessage>
  );
}

/**
 * Custom image component that handles artifact URLs
 */
function MessageImage({
  src,
  alt,
  threadId,
  maxWidth = "90%",
  ...props
}: React.ImgHTMLAttributes<HTMLImageElement> & {
  threadId: string;
  maxWidth?: string;
}) {
  if (!src) return null;

  const imgClassName = cn("overflow-hidden rounded-lg", `max-w-[${maxWidth}]`);

  if (typeof src !== "string") {
    return <img className={imgClassName} src={src} alt={alt} {...props} />;
  }

  const normalizedSrc = (() => {
    const trimmed = src.trim();
    if (
      !trimmed ||
      trimmed.startsWith("/") ||
      trimmed.includes("://") ||
      trimmed.startsWith("data:") ||
      trimmed.startsWith("blob:")
    ) {
      return src;
    }
    if (/^[^/\s][^/\n]*\.(png|jpg|jpeg|webp|svg|gif|bmp)$/i.test(trimmed)) {
      return `/mnt/user-data/outputs/${trimmed}`;
    }
    return src;
  })();

  const url = normalizedSrc.startsWith("/mnt/")
    ? resolveArtifactURL(normalizedSrc, threadId)
    : normalizedSrc;
  const [imageSrc, setImageSrc] = useState(url);

  useEffect(() => {
    if (typeof url !== "string") {
      setImageSrc(String(url));
      return;
    }

    setImageSrc(url);

    // For protected artifact endpoints, fetch with Bearer token and render via blob URL.
    if (!url.includes("/api/threads/")) return;
    const token = getToken();
    if (!token) return;

    let cancelled = false;
    let blobUrl: string | null = null;

    void fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then(async (res) => {
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        blobUrl = URL.createObjectURL(blob);
        setImageSrc(blobUrl);
      })
      .catch(() => {
        // Keep original URL fallback when fetch fails.
      });

    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [url]);

  return (
    <a href={imageSrc} target="_blank" rel="noopener noreferrer">
      <img className={imgClassName} src={imageSrc} alt={alt} {...props} />
    </a>
  );
}

function MessageContent_({
  className,
  message,
  isLoading = false,
  threadId,
  answerFinishedAt,
  answerDurationMs,
}: {
  className?: string;
  message: Message;
  isLoading?: boolean;
  threadId: string;
  answerFinishedAt?: string;
  answerDurationMs?: number;
}) {
  const rehypePlugins = useRehypeSplitWordsIntoSpans(isLoading);
  const isHuman = message.type === "human";
  const components = useMemo(
    () => ({
      img: (props: ImgHTMLAttributes<HTMLImageElement>) => (
        <MessageImage {...props} threadId={threadId} maxWidth="90%" />
      ),
      a: ({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => {
        if (href?.startsWith("/mnt/")) {
          const url = resolveArtifactURL(href, threadId);
          return (
            <a
              {...props}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
            />
          );
        }
        return <a {...props} href={href} />;
      },
    }),
    [threadId],
  );

  const rawContent = extractContentFromMessage(message);
  const reasoningContent = extractReasoningContentFromMessage(message);

  const files = useMemo(() => {
    const files = message.additional_kwargs?.files;
    if (!Array.isArray(files) || files.length === 0) {
      if (rawContent.includes("<uploaded_files>")) {
        // If the content contains the <uploaded_files> tag, we return the parsed files from the content for backward compatibility.
        return parseUploadedFiles(rawContent);
      }
      return null;
    }
    return files as FileInMessage[];
  }, [message.additional_kwargs?.files, rawContent]);

  const contentToDisplay = useMemo(() => {
    if (isHuman) {
      return rawContent ? stripUploadedFilesTag(rawContent) : "";
    }
    return rawContent ?? "";
  }, [rawContent, isHuman]);

  // Image paths from present_files in this message (skill flow: script writes to outputs, agent calls present_files)
  const imagePathsFromPresentFiles = useMemo(() => {
    const paths = extractPresentFilesFromMessage(message);
    return paths.filter((p) => /\.(svg|png|jpe?g|webp)$/i.test(p));
  }, [message]);

  // Replace MOLECULAR_IMAGE_ID with Markdown image. Prefer artifact URL when this message presented an image (skill flow).
  const contentWithMolecularImages = useMemo(() => {
    if (!contentToDisplay) return "";
    const firstImageArtifact =
      threadId && imagePathsFromPresentFiles.length > 0
        ? resolveArtifactURL(imagePathsFromPresentFiles[0]!, threadId)
        : null;
    return contentToDisplay.replace(
      /<!--\s*MOLECULAR_IMAGE_ID:([a-f0-9-]+)\s*-->/gi,
      (_, imageId) =>
        firstImageArtifact
          ? `\n\n![2D分子结构图](${firstImageArtifact})\n\n`
          : `\n\n![2D分子结构图](/molecular_images/${imageId}.svg)\n\n`,
    );
  }, [contentToDisplay, threadId, imagePathsFromPresentFiles]);
  const answerMeta = useMemo(() => {
    if (!answerFinishedAt) {
      return null;
    }
    const finishedMs = Date.parse(answerFinishedAt);
    const finishedLabel = Number.isNaN(finishedMs)
      ? answerFinishedAt
      : new Date(finishedMs).toLocaleString();
    const durationLabel =
      typeof answerDurationMs === "number"
        ? `${(answerDurationMs / 1000).toFixed(1)}s`
        : null;
    return {
      finishedLabel,
      durationLabel,
    };
  }, [answerDurationMs, answerFinishedAt]);
  const userSentMeta = useMemo(() => {
    if (!isHuman) {
      return null;
    }
    const raw = message.additional_kwargs?.client_sent_at;
    if (typeof raw !== "string" || !raw) {
      return null;
    }
    const sentMs = Date.parse(raw);
    return Number.isNaN(sentMs) ? raw : new Date(sentMs).toLocaleString();
  }, [isHuman, message.additional_kwargs?.client_sent_at]);

  const filesList =
    files && files.length > 0 ? (
      <RichFilesList files={files} threadId={threadId} />
    ) : null;

  // Uploading state: mock AI message shown while files upload
  if (message.additional_kwargs?.element === "task") {
    return (
      <AIElementMessageContent className={className}>
        <Task defaultOpen={false}>
          <TaskTrigger title="">
            <div className="text-muted-foreground flex w-full cursor-default items-center gap-2 text-sm select-none">
              <Loader className="size-4" />
              <span>{contentToDisplay}</span>
            </div>
          </TaskTrigger>
        </Task>
      </AIElementMessageContent>
    );
  }

  // Reasoning-only AI message (no main response content yet)
  if (!isHuman && reasoningContent && !rawContent) {
    return (
      <AIElementMessageContent className={className}>
        <Reasoning isStreaming={isLoading}>
          <ReasoningTrigger />
          <ReasoningContent>{reasoningContent}</ReasoningContent>
        </Reasoning>
      </AIElementMessageContent>
    );
  }

  if (isHuman) {
    const messageResponse = contentToDisplay ? (
      <AIElementMessageResponse
        remarkPlugins={humanMessagePlugins.remarkPlugins}
        rehypePlugins={humanMessagePlugins.rehypePlugins}
        components={components}
        parseIncompleteMarkdown={false}
      >
        {contentToDisplay}
      </AIElementMessageResponse>
    ) : null;
    return (
      <div className={cn("ml-auto flex flex-col gap-2", className)}>
        {filesList}
        {messageResponse && (
          <AIElementMessageContent className="w-fit">
            {messageResponse}
          </AIElementMessageContent>
        )}
        {userSentMeta && !isLoading && (
          <div className="text-muted-foreground text-right text-xs">
            提问时间：{userSentMeta}
          </div>
        )}
      </div>
    );
  }

  return (
    <AIElementMessageContent className={className}>
      {filesList}
      <MarkdownContent
        content={contentWithMolecularImages}
        isLoading={isLoading}
        rehypePlugins={[...rehypePlugins, [rehypeKatex, { output: "html" }]]}
        className="my-3"
        components={components}
      />
      {threadId && imagePathsFromPresentFiles.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {imagePathsFromPresentFiles.map((path) => (
            <MessageImage
              key={path}
              src={path}
              alt="2D分子结构图"
              threadId={threadId}
              maxWidth="90%"
            />
          ))}
        </div>
      )}
      {answerMeta && !isLoading && (
        <div className="text-muted-foreground mt-2 text-xs">
          回答完成时间：{answerMeta.finishedLabel}
          {answerMeta.durationLabel ? ` · 耗时 ${answerMeta.durationLabel}` : ""}
        </div>
      )}
    </AIElementMessageContent>
  );
}

/**
 * Get file extension and check helpers
 */
const getFileExt = (filename: string) =>
  filename.split(".").pop()?.toLowerCase() ?? "";

const FILE_TYPE_MAP: Record<string, string> = {
  json: "JSON",
  csv: "CSV",
  txt: "TXT",
  md: "Markdown",
  py: "Python",
  js: "JavaScript",
  ts: "TypeScript",
  tsx: "TSX",
  jsx: "JSX",
  html: "HTML",
  css: "CSS",
  xml: "XML",
  yaml: "YAML",
  yml: "YAML",
  pdf: "PDF",
  png: "PNG",
  jpg: "JPG",
  jpeg: "JPEG",
  gif: "GIF",
  svg: "SVG",
  zip: "ZIP",
  tar: "TAR",
  gz: "GZ",
};

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"];

function getFileTypeLabel(filename: string): string {
  const ext = getFileExt(filename);
  return FILE_TYPE_MAP[ext] ?? (ext.toUpperCase() || "FILE");
}

function isImageFile(filename: string): boolean {
  return IMAGE_EXTENSIONS.includes(getFileExt(filename));
}

/**
 * Format bytes to human-readable size string
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return "—";
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

/**
 * List of files from additional_kwargs.files (with optional upload status)
 */
function RichFilesList({
  files,
  threadId,
}: {
  files: FileInMessage[];
  threadId: string;
}) {
  if (files.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap justify-end gap-2">
      {files.map((file, index) => (
        <RichFileCard
          key={`${file.filename}-${index}`}
          file={file}
          threadId={threadId}
        />
      ))}
    </div>
  );
}

/**
 * Single file card that handles FileInMessage (supports uploading state)
 */
function RichFileCard({
  file,
  threadId,
}: {
  file: FileInMessage;
  threadId: string;
}) {
  const { t } = useI18n();
  const isUploading = file.status === "uploading";
  const isImage = isImageFile(file.filename);

  if (isUploading) {
    return (
      <div className="bg-background border-border/40 flex max-w-50 min-w-30 flex-col gap-1 rounded-lg border p-3 opacity-60 shadow-sm">
        <div className="flex items-start gap-2">
          <Loader2Icon className="text-muted-foreground mt-0.5 size-4 shrink-0 animate-spin" />
          <span
            className="text-foreground truncate text-sm font-medium"
            title={file.filename}
          >
            {file.filename}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <Badge
            variant="secondary"
            className="rounded px-1.5 py-0.5 text-[10px] font-normal"
          >
            {getFileTypeLabel(file.filename)}
          </Badge>
          <span className="text-muted-foreground text-[10px]">
            {t.uploads.uploading}
          </span>
        </div>
      </div>
    );
  }

  if (!file.path) return null;

  const fileUrl = resolveArtifactURL(file.path, threadId);

  if (isImage) {
    return (
      <a
        href={fileUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="group border-border/40 relative block overflow-hidden rounded-lg border"
      >
        <img
          src={fileUrl}
          alt={file.filename}
          className="h-32 w-auto max-w-60 object-cover transition-transform group-hover:scale-105"
        />
      </a>
    );
  }

  return (
    <div className="bg-background border-border/40 flex max-w-50 min-w-30 flex-col gap-1 rounded-lg border p-3 shadow-sm">
      <div className="flex items-start gap-2">
        <FileIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <span
          className="text-foreground truncate text-sm font-medium"
          title={file.filename}
        >
          {file.filename}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <Badge
          variant="secondary"
          className="rounded px-1.5 py-0.5 text-[10px] font-normal"
        >
          {getFileTypeLabel(file.filename)}
        </Badge>
        <span className="text-muted-foreground text-[10px]">
          {formatBytes(file.size)}
        </span>
      </div>
    </div>
  );
}

const MessageContent = memo(MessageContent_);
