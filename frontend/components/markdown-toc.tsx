"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { extractMarkdownHeadings } from "@/lib/markdown-headings";

type MarkdownTocProps = {
  content: string;
};

function revealTocItem(
  nav: HTMLElement,
  headingId: string,
  behavior: ScrollBehavior,
) {
  const item = nav.querySelector<HTMLElement>(
    `[data-toc-heading="${headingId}"]`,
  );
  if (!item) return;
  const navBounds = nav.getBoundingClientRect();
  const itemBounds = item.getBoundingClientRect();
  const inset = 12;
  if (
    itemBounds.top >= navBounds.top + inset
    && itemBounds.bottom <= navBounds.bottom - inset
  ) return;
  nav.scrollTo({
    top: item.offsetTop - nav.clientHeight / 2 + item.offsetHeight / 2,
    behavior,
  });
}

export function MarkdownToc({ content }: MarkdownTocProps) {
  const headings = useMemo(() => extractMarkdownHeadings(content), [content]);
  const [activeId, setActiveId] = useState(headings[0]?.id ?? "");
  const navRef = useRef<HTMLElement>(null);
  const resolvedActiveId = headings.some((heading) => heading.id === activeId)
    ? activeId
    : headings[0]?.id ?? "";

  useEffect(() => {
    const scrollRoot = navRef.current?.closest(".knowledge-reader");
    if (!(scrollRoot instanceof HTMLElement) || headings.length === 0) return;
    const root = scrollRoot;

    function updateActiveHeading() {
      const rootTop = root.getBoundingClientRect().top + 80;
      let nextId = headings[0].id;
      headings.forEach((heading) => {
        const element = document.getElementById(heading.id);
        if (element && element.getBoundingClientRect().top <= rootTop) {
          nextId = heading.id;
        }
      });
      setActiveId(nextId);
      const nav = navRef.current;
      if (nav) revealTocItem(nav, nextId, "auto");
    }

    const frame = window.requestAnimationFrame(updateActiveHeading);
    root.addEventListener("scroll", updateActiveHeading, { passive: true });
    window.addEventListener("resize", updateActiveHeading);
    return () => {
      window.cancelAnimationFrame(frame);
      root.removeEventListener("scroll", updateActiveHeading);
      window.removeEventListener("resize", updateActiveHeading);
    };
  }, [headings]);

  if (headings.length === 0) return null;

  return (
    <nav className="knowledge-article-toc" aria-label="本文目录" ref={navRef}>
      <strong>本文目录</strong>
      <ol>
        {headings.map((heading) => (
          <li
            className={resolvedActiveId === heading.id ? "active" : ""}
            data-toc-heading={heading.id}
            key={heading.id}
            style={{ paddingLeft: `${Math.max(0, heading.level - 1) * 10}px` }}
          >
            <a
              href={`#${heading.id}`}
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(heading.id)?.scrollIntoView({
                  behavior: "smooth",
                  block: "start",
                });
                setActiveId(heading.id);
                const nav = navRef.current;
                if (nav) revealTocItem(nav, heading.id, "smooth");
              }}
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
