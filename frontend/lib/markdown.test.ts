import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { extractMarkdownHeadings } from "./markdown-headings.ts";
import { markdownSanitizeSchema } from "./markdown-sanitize.ts";

const sample = `# 一级标题

## 二级标题

- 无序列表
1. 有序列表

> 引用

**粗体**、*斜体*、~~删除线~~和\`行内代码\`

\`\`\`text
代码块
\`\`\`

[链接](https://example.com)

![图片](https://example.com/image.png)

- [x] 已完成

| 名称 | 数值 |
| --- | ---: |
| 示例 | 1 |
`;

test("React Markdown with GFM renders the documented syntax", () => {
  const html = renderToStaticMarkup(createElement(ReactMarkdown, {
    remarkPlugins: [remarkGfm],
    children: sample,
  }));

  for (const tag of ["h1", "h2", "ul", "ol", "blockquote", "strong", "em", "del", "code", "pre", "a", "img", "table"]) {
    assert.match(html, new RegExp(`<${tag}(?: |>)`));
  }
  assert.match(html, /type="checkbox"/);
});

test("renders allowed HTML and removes unsafe HTML, styles, events, and classes", () => {
  const html = renderToStaticMarkup(createElement(ReactMarkdown, {
    rehypePlugins: [rehypeRaw, [rehypeSanitize, markdownSanitizeSchema]],
    children: `<details open onclick="alert(1)">
<summary>展开内容</summary>
<kbd>Ctrl</kbd> <mark>重点</mark> H<sup>2</sup>O<sub>2</sub>
</details>
<div class="md-callout unsafe-class" style="position:fixed">安全提示</div>
<script>alert(1)</script><iframe src="https://example.com"></iframe><style>body{display:none}</style>`,
  }));

  for (const tag of ["details", "summary", "kbd", "mark", "sup", "sub"]) {
    assert.match(html, new RegExp(`<${tag}(?: |>)`));
  }
  assert.match(html, /class="md-callout"/);
  assert.doesNotMatch(html, /onclick=|style=|unsafe-class|<script|<iframe|<style/);
});

test("extracts unique article headings and ignores fenced code", () => {
  const headings = extractMarkdownHeadings(`# 总览

## 重复标题
## 重复标题

副标题
------

\`\`\`
# 代码中的标题
\`\`\`
`);

  assert.deepEqual(
    headings.map(({ id, level, text }) => ({ id, level, text })),
    [
      { id: "article-heading-总览", level: 1, text: "总览" },
      { id: "article-heading-重复标题", level: 2, text: "重复标题" },
      { id: "article-heading-重复标题-2", level: 2, text: "重复标题" },
      { id: "article-heading-副标题", level: 2, text: "副标题" },
    ],
  );
});
