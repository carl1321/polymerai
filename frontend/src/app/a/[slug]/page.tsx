"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BotIcon } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Toaster, toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { PromptInputProvider } from "@/components/ai-elements/prompt-input";
import { SidebarProvider } from "@/components/ui/sidebar";
import { ArtifactsProvider } from "@/components/workspace/artifacts";
import { ChatBox } from "@/components/workspace/chats/chat-box";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { createPublicShareLangGraphClient } from "@/core/api/api-client";
import { fetchPublicMeta } from "@/core/public-agent/api";
import { useLocalSettings } from "@/core/settings";
import { SubtasksProvider } from "@/core/tasks/context";
import { useThreadStream } from "@/core/threads/hooks";
import { uuid } from "@/core/utils/uuid";
import { cn } from "@/lib/utils";

const queryClient = new QueryClient();

type Meta = {
  agent_id: string;
  agent_name: string;
  description: string;
  expires_at: string | null;
};

function PublicChatLoaded({
  slug,
  token,
  meta,
}: {
  slug: string;
  token: string;
  meta: Meta;
}) {
  const [clientThreadId] = useState(() => uuid());
  const [isWelcomeMode, setIsWelcomeMode] = useState(true);
  const [settings, setSettings] = useLocalSettings();

  const langGraphClient = useMemo(
    () => createPublicShareLangGraphClient(slug, token),
    [slug, token],
  );

  const streamContext = useMemo(
    () => ({
      ...settings.context,
      agent_id: meta.agent_id,
    }),
    [settings.context, meta.agent_id],
  );

  const { thread, sendMessage } = useThreadStream({
    threadId: isWelcomeMode ? undefined : clientThreadId,
    context: streamContext,
    langGraphClient,
    onSend: () => {
      setIsWelcomeMode(false);
    },
    onStart: () => {
      setIsWelcomeMode(false);
    },
  });

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      void sendMessage(clientThreadId, message, { agent_id: meta.agent_id });
    },
    [sendMessage, clientThreadId, meta.agent_id],
  );

  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);

  return (
    <ThreadContext.Provider value={{ thread }}>
      <div className="bg-background flex min-h-screen w-full flex-1 flex-col">
        <header className="border-border h-12 shrink-0 border-b px-4">
          <div className="mx-auto flex h-full w-full max-w-3xl items-center gap-2">
            <div className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1">
              <BotIcon className="text-primary h-3.5 w-3.5" />
              <span className="text-xs font-medium">{meta.agent_name}</span>
            </div>
            {meta.description ? (
              <span className="text-muted-foreground line-clamp-1 text-xs">
                {meta.description}
              </span>
            ) : null}
            <span className="text-muted-foreground ml-auto text-[11px]">
              默认有效期 1 天（24 小时）
              {meta.expires_at
                ? ` · 当前链接到期：${new Date(meta.expires_at).toLocaleString()}`
                : ""}
            </span>
          </div>
        </header>
        <main className="relative flex min-h-0 min-h-[calc(100vh-3rem)] flex-1 flex-col">
          <ChatBox threadId={clientThreadId}>
            <div className="mx-auto flex min-h-0 w-full max-w-3xl grow flex-col">
              <div className="flex size-full justify-center">
                <MessageList
                  className={cn("size-full", !isWelcomeMode && "pt-2")}
                  threadId={clientThreadId}
                  thread={thread}
                />
              </div>
              <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-4 pb-4">
                <div
                  className={cn(
                    "relative w-full max-w-3xl",
                    isWelcomeMode && "-translate-y-[calc(50vh-120px)]",
                  )}
                >
                  <InputBox
                    className="bg-background/5 w-full"
                    isWelcomeMode={isWelcomeMode}
                    threadId={clientThreadId}
                    autoFocus={isWelcomeMode}
                    status={thread.isLoading ? "streaming" : "ready"}
                    context={streamContext}
                    publicMinimal
                    publicAllowAttachments
                    onContextChange={(ctx) => setSettings("context", ctx)}
                    onSubmit={(msg) => {
                      try {
                        handleSubmit(msg);
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : String(e));
                      }
                    }}
                    onStop={handleStop}
                  />
                </div>
              </div>
            </div>
          </ChatBox>
        </main>
      </div>
    </ThreadContext.Provider>
  );
}

function PublicAgentGate() {
  const params = useParams<{ slug: string }>();
  const searchParams = useSearchParams();
  const slug = params.slug ?? "";

  const [token, setToken] = useState<string | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    const q = searchParams.get("token");
    const storageKey = `deerflow_public_token_${slug}`;
    if (q) {
      setToken(q);
      try {
        sessionStorage.setItem(storageKey, q);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      const s = sessionStorage.getItem(storageKey);
      if (s) setToken(s);
    } catch {
      /* ignore */
    }
  }, [searchParams, slug]);

  useEffect(() => {
    if (!slug || !token) {
      if (!token) setMetaError("缺少访问令牌：请在分享链接中带上 ?token=… 参数。");
      return;
    }
    let cancelled = false;
    setMetaError(null);
    void fetchPublicMeta(slug, token)
      .then((m) => {
        if (cancelled) return;
        setMeta({
          agent_id: m.agent_id,
          agent_name: m.agent_name,
          description: m.description,
          expires_at: m.expires_at,
        });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setMeta(null);
        setMetaError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [slug, token]);

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <p className="text-muted-foreground max-w-md text-center text-sm">
          {metaError ?? "正在检查链接…"}
        </p>
      </div>
    );
  }

  if (metaError || !meta) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <p className="text-destructive max-w-md text-center text-sm">
          {metaError ?? "加载中…"}
        </p>
      </div>
    );
  }

  return <PublicChatLoaded slug={slug} token={token} meta={meta} />;
}

export default function PublicAgentPage() {
  return (
    <QueryClientProvider client={queryClient}>
      <SidebarProvider>
        <SubtasksProvider>
          <ArtifactsProvider>
            <PromptInputProvider>
              <PublicAgentGate />
            </PromptInputProvider>
          </ArtifactsProvider>
        </SubtasksProvider>
      </SidebarProvider>
      <Toaster position="top-center" />
    </QueryClientProvider>
  );
}
