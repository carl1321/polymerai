"use client";

import { useEffect } from "react";

type ShortcutAction = () => void;

interface Shortcut {
  key: string;
  meta: boolean;
  shift?: boolean;
  action: ShortcutAction;
}

/**
 * Register global keyboard shortcuts on window.
 * Shortcuts are suppressed when focus is inside an input, textarea, or
 * contentEditable element - except for Cmd+K which always fires.
 */
export function useGlobalShortcuts(shortcuts: Shortcut[]) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const meta = event.metaKey || event.ctrlKey;

      const eventKey = event.key?.toLowerCase();
      if (!eventKey) return;

      for (const shortcut of shortcuts) {
        const shortcutKey = shortcut.key?.toLowerCase();
        if (
          !shortcutKey ||
          eventKey !== shortcutKey ||
          meta !== shortcut.meta ||
          (shortcut.shift ?? false) !== event.shiftKey
        ) {
          continue;
        }

        // Allow Cmd+K even in inputs (standard command palette behavior)
        if (shortcut.key !== "k") {
          const target = event.target as HTMLElement;
          const tag = target.tagName;
          if (
            tag === "INPUT" ||
            tag === "TEXTAREA" ||
            target.isContentEditable
          ) {
            continue;
          }
        }

        event.preventDefault();
        shortcut.action();
        return;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts]);
}
