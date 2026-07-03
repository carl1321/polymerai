"use client";

import { python } from "@codemirror/lang-python";
import { StateEffect, StateField } from "@codemirror/state";
import { EditorView, Decoration, lineNumbers } from "@codemirror/view";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useRef } from "react";

import { cn } from "@/lib/utils";

const setErrorLineEffect = StateEffect.define<number | null>();

const errorLineField = StateField.define({
  create() {
    return Decoration.none;
  },
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const effect of tr.effects) {
      if (!effect.is(setErrorLineEffect)) continue;
      const lineNum = effect.value;
      if (lineNum == null || lineNum < 1) return Decoration.none;
      const line = tr.state.doc.line(Math.min(lineNum, tr.state.doc.lines));
      return Decoration.set([
        Decoration.line({ class: "cm-errorLine" }).range(line.from),
      ]);
    }
    return deco;
  },
  provide: (field) => EditorView.decorations.from(field),
});

const errorLineTheme = EditorView.baseTheme({
  ".cm-errorLine": {
    backgroundColor: "rgba(239, 68, 68, 0.14)",
    boxShadow: "inset 0 0 0 2px rgb(239, 68, 68)",
  },
  ".cm-gutterElement.cm-errorGutter": {
    color: "rgb(239, 68, 68)",
    fontWeight: "700",
  },
});

const darkTheme = monokaiInit({
  settings: { background: "transparent", fontSize: "13px" },
});
const lightTheme = basicLightInit({
  settings: { background: "transparent", fontSize: "13px" },
});

export function WorkflowToolCodeEditor({
  value,
  onChange,
  readOnly,
  errorLine,
  className,
}: {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  errorLine?: number | null;
  className?: string;
}) {
  const { resolvedTheme } = useTheme();
  const viewRef = useRef<EditorView | null>(null);

  const extensions = useMemo(
    () => [
      python(),
      lineNumbers(),
      errorLineField,
      errorLineTheme,
      EditorView.lineWrapping,
    ],
    [],
  );

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({ effects: setErrorLineEffect.of(errorLine ?? null) });
    if (errorLine != null && errorLine >= 1) {
      const line = view.state.doc.line(Math.min(errorLine, view.state.doc.lines));
      view.dispatch({
        effects: EditorView.scrollIntoView(line.from, { y: "center" }),
      });
    }
  }, [errorLine, value]);

  return (
    <CodeMirror
      value={value}
      onChange={readOnly ? undefined : onChange}
      readOnly={readOnly}
      theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
      extensions={extensions}
      className={cn(
        "h-full min-h-[280px] overflow-auto font-mono text-sm",
        "[&_.cm-editor]:min-h-[280px] [&_.cm-scroller]:min-h-[280px]",
        errorLine != null && "ring-2 ring-red-500/60 ring-inset rounded-sm",
        className,
      )}
      basicSetup={{
        lineNumbers: false,
        foldGutter: true,
        highlightActiveLine: !readOnly,
      }}
      onCreateEditor={(view) => {
        viewRef.current = view;
        view.dispatch({ effects: setErrorLineEffect.of(errorLine ?? null) });
      }}
    />
  );
}
