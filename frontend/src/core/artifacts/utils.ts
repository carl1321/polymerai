import { getBackendBaseURL } from "../config";
import { isStaticWebsiteOnly } from "../static-mode";
import type { AgentThread } from "../threads";

function artifactQueryParams({
  download,
  preview,
}: {
  download?: boolean;
  preview?: boolean;
}) {
  const params = new URLSearchParams();
  if (download) params.set("download", "true");
  if (preview) params.set("preview", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function urlOfArtifact({
  filepath,
  threadId,
  download = false,
  preview = false,
  isMock = false,
}: {
  filepath: string;
  threadId: string;
  download?: boolean;
  preview?: boolean;
  isMock?: boolean;
}) {
  if (isStaticWebsiteOnly()) {
    return staticDemoArtifactURL({ filepath, threadId, download });
  }
  const qs = artifactQueryParams({ download, preview });
  if (isMock) {
    return `${getBackendBaseURL()}/mock/api/threads/${threadId}/artifacts${filepath}${qs}`;
  }
  return `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${filepath}${qs}`;
}

export function extractArtifactsFromThread(thread: AgentThread) {
  return thread.values.artifacts ?? [];
}

export function resolveArtifactURL(absolutePath: string, threadId: string) {
  if (isStaticWebsiteOnly()) {
    return staticDemoArtifactURL({ filepath: absolutePath, threadId });
  }
  return `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${absolutePath}`;
}

function staticDemoArtifactURL({
  filepath,
  threadId,
  download = false,
}: {
  filepath: string;
  threadId: string;
  download?: boolean;
}) {
  const demoPath = filepath.replace(/^\/mnt\//, "/");
  return `${getBackendBaseURL()}/demo/threads/${threadId}${demoPath}${download ? "?download=true" : ""}`;
}
