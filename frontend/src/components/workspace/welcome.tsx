"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

let waved = false;

export function Welcome({
  className,
  mode,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
}) {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const isUltra = useMemo(() => mode === "ultra", [mode]);
  const skillMode = searchParams.get("mode") === "skill";
  const hasSpecificSkill = Boolean(
    (searchParams.get("skill_name") || "").trim(),
  );
  const showSkillCreateWelcome = skillMode && !hasSpecificSkill;
  const colors = useMemo(() => {
    if (isUltra) {
      return ["#efefbb", "#e9c665", "#e3a812"];
    }
    return ["var(--color-foreground)"];
  }, [isUltra]);
  useEffect(() => {
    waved = true;
  }, []);
  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
        className,
      )}
    >
      <div className="text-2xl font-bold">
        {showSkillCreateWelcome ? (
          `✨ ${t.welcome.createYourOwnSkill} ✨`
        ) : (
          <div className="flex items-center gap-2">
            <div className={cn("inline-block", !waved ? "animate-wave" : "")}>
              {isUltra ? "🚀" : "👋"}
            </div>
            <AuroraText colors={colors}>{t.welcome.greeting}</AuroraText>
          </div>
        )}
      </div>
      <div className="text-muted-foreground text-sm">
        {(showSkillCreateWelcome
          ? t.welcome.createYourOwnSkillDescription
          : t.welcome.description
        ).includes("\n") ? (
          <pre className="font-sans whitespace-pre">
            {showSkillCreateWelcome
              ? t.welcome.createYourOwnSkillDescription
              : t.welcome.description}
          </pre>
        ) : (
          <p>
            {showSkillCreateWelcome
              ? t.welcome.createYourOwnSkillDescription
              : t.welcome.description}
          </p>
        )}
      </div>
    </div>
  );
}
