import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  /**
   * Specify your server-side environment variables schema here. This way you can ensure the app
   * isn't built with invalid env vars.
   */
  server: {
    GITHUB_OAUTH_TOKEN: z.string().optional(),
    NODE_ENV: z
      .enum(["development", "test", "production"])
      .default("development"),
  },

  /**
   * Specify your client-side environment variables schema here. This way you can ensure the app
   * isn't built with invalid env vars. To expose them to the client, prefix them with
   * `NEXT_PUBLIC_`.
   */
  client: {
    NEXT_PUBLIC_BACKEND_BASE_URL: z.string().optional(),
    NEXT_PUBLIC_LANGGRAPH_BASE_URL: z.string().optional(),
    NEXT_PUBLIC_STATIC_WEBSITE_ONLY: z.string().optional(),
    /** Milliseconds between async_tasks list refreshes while a thread chat is open (0 = off). Max 10m. */
    NEXT_PUBLIC_ASYNC_TASK_UI_POLL_MS: z.preprocess((x) => {
      if (x === undefined || x === null || x === "") {
        return undefined;
      }
      const n = typeof x === "number" ? x : parseInt(String(x).trim(), 10);
      return Number.isFinite(n) ? n : undefined;
    }, z.number().int().min(0).max(600_000).optional()),
  },

  /**
   * You can't destruct `process.env` as a regular object in the Next.js edge runtimes (e.g.
   * middlewares) or client-side so we need to destruct manually.
   */
  runtimeEnv: {
    NODE_ENV: process.env.NODE_ENV,

    NEXT_PUBLIC_BACKEND_BASE_URL: process.env.NEXT_PUBLIC_BACKEND_BASE_URL,
    NEXT_PUBLIC_LANGGRAPH_BASE_URL: process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL,
    NEXT_PUBLIC_STATIC_WEBSITE_ONLY:
      process.env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY,
    NEXT_PUBLIC_ASYNC_TASK_UI_POLL_MS:
      process.env.NEXT_PUBLIC_ASYNC_TASK_UI_POLL_MS,
    GITHUB_OAUTH_TOKEN: process.env.GITHUB_OAUTH_TOKEN,
  },
  /**
   * Run `build` or `dev` with `SKIP_ENV_VALIDATION` to skip env validation. This is especially
   * useful for Docker builds.
   */
  skipValidation: !!process.env.SKIP_ENV_VALIDATION,
  /**
   * Makes it so that empty strings are treated as undefined. `SOME_VAR: z.string()` and
   * `SOME_VAR=''` will throw an error.
   */
  emptyStringAsUndefined: true,
});
