import { config as dotenvConfig } from "dotenv";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// frontend/scripts -> ../.env (repo root)
const rootEnvPath = path.resolve(__dirname, "..", ".env");
if (fs.existsSync(rootEnvPath)) {
  dotenvConfig({
    path: rootEnvPath,
    // 让根目录配置优先级最高，避免前面别的 env_file/系统变量覆盖
    override: true,
  });
}

// Compatibility: repo root .env uses NEXT_PUBLIC_API_URL, but frontend expects NEXT_PUBLIC_BACKEND_BASE_URL
if (!process.env.NEXT_PUBLIC_BACKEND_BASE_URL && process.env.NEXT_PUBLIC_API_URL) {
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL = process.env.NEXT_PUBLIC_API_URL;
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: next-with-root-env.mjs <cmd> [args...]");
  process.exit(1);
}

const cmd = args[0];
const cmdArgs = args.slice(1);

const frontendBin = path.resolve(__dirname, "..", "node_modules", ".bin");
const env = {
  ...process.env,
  PATH: `${frontendBin}${path.delimiter}${process.env.PATH ?? ""}`,
};

const child = spawn(cmd, cmdArgs, {
  stdio: "inherit",
  env,
  shell: true,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});

