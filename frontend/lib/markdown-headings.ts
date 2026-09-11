export type MarkdownHeading = {
  id: string;
  level: number;
  text: string;
  line: number;
};

function headingText(value: string) {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/[\\*_~]/g, "")
    .trim();
}

function headingSlug(value: string) {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase()
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^\p{L}\p{N}_.-]/gu, "");
}

export function extractMarkdownHeadings(content: string): MarkdownHeading[] {
  const headings: MarkdownHeading[] = [];
  const slugCounts = new Map<string, number>();
  const lines = content.split(/\r?\n/);
  let fence: { marker: string; length: number } | null = null;

  function append(level: number, rawText: string, line: number) {
    const text = headingText(rawText.replace(/[ \t]+#+[ \t]*$/, ""));
    if (!text) return;
    const baseSlug = headingSlug(text) || `section-${line}`;
    const count = slugCounts.get(baseSlug) ?? 0;
    slugCounts.set(baseSlug, count + 1);
    headings.push({
      id: `article-heading-${baseSlug}${count ? `-${count + 1}` : ""}`,
      level,
      text,
      line,
    });
  }

  lines.forEach((line, index) => {
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (fenceMatch) {
      const marker = fenceMatch[1][0];
      if (fence === null) {
        fence = { marker, length: fenceMatch[1].length };
      } else if (fence.marker === marker && fenceMatch[1].length >= fence.length) {
        fence = null;
      }
      return;
    }
    if (fence !== null) return;

    const atxMatch = line.match(/^ {0,3}(#{1,6})[ \t]+(.+?)\s*$/);
    if (atxMatch) {
      append(atxMatch[1].length, atxMatch[2], index + 1);
      return;
    }

    const underline = lines[index + 1]?.match(/^ {0,3}(=+|-+)\s*$/);
    if (line.trim() && underline) {
      append(underline[1][0] === "=" ? 1 : 2, line, index + 1);
    }
  });

  return headings;
}
