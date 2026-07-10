// Maps a file path's extension to the Prism grammar key registered in
// citation-card.tsx. The backend's SearchResultItem/Citation shapes
// don't carry a language field, and file extension is a reliable
// enough signal for picking a highlighting grammar — this never needs
// to be more precise than that.
const EXTENSION_TO_LANGUAGE: Record<string, string> = {
  py: "python",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  tsx: "tsx",
  go: "go",
  java: "java",
  json: "json",
  yml: "yaml",
  yaml: "yaml",
  md: "markdown",
  markdown: "markdown",
  sh: "bash",
  bash: "bash",
};

export function detectLanguageFromPath(filePath: string): string | null {
  const match = /\.([^./]+)$/.exec(filePath);
  if (!match) return null;
  return EXTENSION_TO_LANGUAGE[match[1].toLowerCase()] ?? null;
}
