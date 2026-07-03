"use client";

import { syntaxTree } from "@codemirror/language";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { languages } from "@codemirror/language-data";
import type { Range } from "@codemirror/state";
import { Decoration, EditorView, ViewPlugin } from "@codemirror/view";
import type { DecorationSet } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import { useTheme } from "next-themes";
import { useMemo } from "react";

import { cn } from "@/lib/utils";

const PROMPT_H1_CLASS = "prompt-editor-h1";
const PROMPT_H2_CLASS = "prompt-editor-h2";
const PROMPT_H3_CLASS = "prompt-editor-h3";

/** 根据语法树为 Markdown 标题行添加装饰（# ## ### 显示为有色、加粗、加大） */
const promptHeadingDecorator = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = this.buildDecorations(view);
    }

    update(update: { docChanged: boolean; view: EditorView }) {
      if (update.docChanged) {
        this.decorations = this.buildDecorations(update.view);
      }
    }

    buildDecorations(view: EditorView): DecorationSet {
      const decorations: Range<Decoration>[] = [];
      const tree = syntaxTree(view.state);
      tree.iterate({
        enter: (node) => {
          const name = node.type.name;
          let cls: string | null = null;
          if (name === "ATXHeading1" || name === "SetextHeading1") cls = PROMPT_H1_CLASS;
          else if (name === "ATXHeading2" || name === "SetextHeading2") cls = PROMPT_H2_CLASS;
          else if (name === "ATXHeading3" || name === "SetextHeading3") cls = PROMPT_H3_CLASS;
          if (cls) {
            decorations.push(Decoration.mark({ class: cls }).range(node.from, node.to));
          }
        },
      });
      return Decoration.set(decorations, true);
    }
  },
  { decorations: (v) => v.decorations },
);

/** 主题：标题类名对应 #2d9c8c 颜色、加粗、字号加大 */
const promptHeadingTheme = EditorView.theme({
  [`& .${PROMPT_H1_CLASS}`]: {
    color: "#2d9c8c",
    fontWeight: "bold",
    fontSize: "1.15em",
  },
  [`& .${PROMPT_H2_CLASS}`]: {
    color: "#2d9c8c",
    fontWeight: "bold",
    fontSize: "1.08em",
  },
  [`& .${PROMPT_H3_CLASS}`]: {
    color: "#2d9c8c",
    fontWeight: "bold",
  },
  "&.dark .prompt-editor-h1, &.dark .prompt-editor-h2, &.dark .prompt-editor-h3": {
    color: "rgb(45 212 191)",
  },
});

const customLightTheme = basicLightInit({
  settings: {
    background: "transparent",
    fontSize: "14px",
  },
});

const customDarkTheme = monokaiInit({
  settings: {
    background: "transparent",
    gutterBackground: "transparent",
    gutterForeground: "#555",
    gutterActiveForeground: "#fff",
    fontSize: "14px",
  },
});

export function PromptRichEditor({
  value,
  onChange,
  placeholder,
  className,
  minHeight = "320px",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  minHeight?: string;
}) {
  const { resolvedTheme } = useTheme();

  const extensions = useMemo(
    () => [
      markdown({
        base: markdownLanguage,
        codeLanguages: languages,
      }),
      promptHeadingDecorator,
      promptHeadingTheme,
      EditorView.lineWrapping,
    ],
    [],
  );

  return (
    <div className={cn("prompt-rich-editor rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600", className)}>
      <CodeMirror
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        theme={resolvedTheme === "dark" ? customDarkTheme : customLightTheme}
        extensions={extensions}
        basicSetup={{
          lineNumbers: false,
          foldGutter: false,
          highlightActiveLine: false,
          highlightActiveLineGutter: false,
        }}
        className={cn(
          "text-sm font-mono w-full [&_.cm-editor]:min-h-[320px] [&_.cm-scroller]:overflow-auto",
          "[&_.cm-focused]:outline-none [&_.cm-content]:leading-relaxed",
        )}
        style={{ minHeight }}
      />
    </div>
  );
}
