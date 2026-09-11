"use client";

import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import { extractMarkdownHeadings } from "@/lib/markdown-headings";
import { markdownSanitizeSchema } from "@/lib/markdown-sanitize";

type MarkdownRendererProps = {
  content: string;
  className?: string;
  emptyText?: string;
};

function normalizeLatexDelimiters(content: string) {
  return content
    .split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g)
    .map((segment, index) => {
      if (index % 2 === 1) return segment;
      return segment
        .replace(/\\{1,2}\[([\s\S]*?)\\{1,2}\]/g, (_match, expression: string) => (
          `$$${expression}$$`
        ))
        .replace(/\\{1,2}\((.*?)\\{1,2}\)/g, (_match, expression: string) => (
          `$${expression.trim()}$`
        ));
    })
    .join("");
}

export function MarkdownRenderer({
  content,
  className = "",
  emptyText,
}: MarkdownRendererProps) {
  if (!content.trim()) {
    return emptyText ? <p className="markdown-empty">{emptyText}</p> : null;
  }

  const headingIdsByLine = new Map(
    extractMarkdownHeadings(content).map((heading) => [heading.line, heading.id]),
  );
  const normalizedContent = normalizeLatexDelimiters(content);
  function headingComponent(
    Tag: "h1" | "h2" | "h3" | "h4" | "h5" | "h6",
  ): NonNullable<Components["h1"]> {
    return function MarkdownHeading({ node, children, ...props }) {
      const id = node?.position?.start.line
        ? headingIdsByLine.get(node.position.start.line)
        : undefined;
      return <Tag {...props} id={id}>{children}</Tag>;
    };
  }

  return (
    <div className={["markdown-content", className].filter(Boolean).join(" ")}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[
          rehypeRaw,
          [rehypeSanitize, markdownSanitizeSchema],
          [rehypeKatex, { strict: false }],
        ]}
        components={{
          h1: headingComponent("h1"),
          h2: headingComponent("h2"),
          h3: headingComponent("h3"),
          h4: headingComponent("h4"),
          h5: headingComponent("h5"),
          h6: headingComponent("h6"),
          a({ children, ...props }) {
            return (
              <a {...props} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            );
          },
          img({ alt, ...props }) {
            return <img {...props} alt={alt ?? ""} loading="lazy" />;
          },
          table({ children, ...props }) {
            return (
              <div className="markdown-table-wrap">
                <table {...props}>{children}</table>
              </div>
            );
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
