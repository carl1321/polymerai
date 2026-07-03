/** 从 Python 报错 / traceback 中解析 tool.py 内的行号（1-based） */
export function parsePythonErrorLine(text: string): number | null {
  if (!text.trim()) return null;

  const toolPyFrames: number[] = [];
  const frameRe = /File\s+["'][^"']*tool\.py["'],\s*line\s+(\d+)/gi;
  let m: RegExpExecArray | null;
  while ((m = frameRe.exec(text)) !== null) {
    const lineStr = m[1];
    if (lineStr) toolPyFrames.push(Number.parseInt(lineStr, 10));
  }
  const lastFrame = toolPyFrames.at(-1);
  if (lastFrame !== undefined) {
    return lastFrame;
  }

  const syntaxRe = /(?:^|\n)\s*File\s+["'][^"']*tool\.py["'],\s*line\s+(\d+)/im;
  const syntax = syntaxRe.exec(text);
  if (syntax?.[1]) return Number.parseInt(syntax[1], 10);

  const genericLine = /line\s+(\d+)/i.exec(text);
  if (genericLine?.[1]) {
    const line = Number.parseInt(genericLine[1], 10);
    if (line > 0 && line < 10_000) return line;
  }

  return null;
}
