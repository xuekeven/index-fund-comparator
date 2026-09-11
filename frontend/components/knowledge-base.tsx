"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";

import {
  createKnowledgeArticle,
  deleteKnowledgeArticle,
  getContentOptions,
  getKnowledgeArticles,
  reorderKnowledgeArticles,
  updateContentOptions,
  updateKnowledgeArticle,
} from "@/lib/api";
import type {
  KnowledgeArticle,
  KnowledgeArticlePayload,
  KnowledgeCategoryOrder,
  KnowledgeSource,
} from "@/lib/types";
import { ContentOptionDialog } from "./content-option-dialog";
import { ArrowUpIcon, CloseIcon, SearchIcon, SettingsIcon } from "./icons";
import { NoteSelect } from "./investment-notes";
import { MarkdownRenderer } from "./markdown-renderer";
import { MarkdownToc } from "./markdown-toc";

const DEFAULT_CATEGORIES = ["资产配置", "利率", "债券", "黄金", "红利策略", "交易工具"];
const ARTICLE_HASH_PATTERN = /^#knowledge\/article\/(\d+)$/;

function articleIdFromUrl() {
  const match = window.location.hash.match(ARTICLE_HASH_PATTERN);
  if (!match) return null;
  const articleId = Number(match[1]);
  return Number.isSafeInteger(articleId) ? articleId : null;
}

function articleHash(articleId: number) {
  return `#knowledge/article/${articleId}`;
}

type DragItem =
  | { type: "category"; category: string }
  | { type: "article"; articleId: number };
type DropTarget =
  | { type: "category"; category: string; position: "before" | "after" }
  | { type: "article"; articleId: number; position: "before" | "after" }
  | { type: "category-content"; category: string }
  | null;
type ArticleDraft = KnowledgeArticlePayload;

function emptyDraft(categoryOptions: string[] = DEFAULT_CATEGORIES): ArticleDraft {
  return {
    title: "",
    category: categoryOptions[0] ?? "",
    summary: "",
    contentMarkdown: "",
    tags: [],
    sources: [{ name: "", url: null }],
    reviewedAt: null,
  };
}

function toDraft(article: KnowledgeArticle): ArticleDraft {
  return {
    title: article.title,
    category: article.category,
    summary: "",
    contentMarkdown: article.contentMarkdown,
    tags: article.tags,
    sources: article.sources.length > 0
      ? article.sources
      : [{ name: "", url: null }],
    reviewedAt: article.reviewedAt,
  };
}

function splitTags(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[、,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function orderGroups(items: KnowledgeArticle[]): KnowledgeCategoryOrder[] {
  const groups = new Map<string, number[]>();
  items.forEach((article) => {
    const ids = groups.get(article.category) ?? [];
    ids.push(article.id);
    groups.set(article.category, ids);
  });
  return Array.from(groups, ([category, articleIds]) => ({ category, articleIds }));
}

export function KnowledgeBase() {
  const [articles, setArticles] = useState<KnowledgeArticle[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<KnowledgeArticle | "new" | null>(null);
  const [inlineBodyDraft, setInlineBodyDraft] = useState<{
    articleId: number;
    content: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeArticle | null>(null);
  const [managingCategories, setManagingCategories] = useState(false);
  const [draft, setDraft] = useState<ArticleDraft>(emptyDraft);
  const [openSelect, setOpenSelect] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [categoryOptions, setCategoryOptions] = useState<string[]>(DEFAULT_CATEGORIES);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [reordering, setReordering] = useState(false);
  const [dragItem, setDragItem] = useState<DragItem | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTarget>(null);
  const [error, setError] = useState<string | null>(null);
  const readerRef = useRef<HTMLElement>(null);
  const inlineBodyInputRef = useRef<HTMLTextAreaElement>(null);
  const inlineBodyScrollRatioRef = useRef(0);
  const restoreReaderScrollRef = useRef(false);
  const deleteConfirmRef = useRef<HTMLButtonElement>(null);
  const inlineBodyArticleId = inlineBodyDraft?.articleId ?? null;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getKnowledgeArticles(controller.signal),
      getContentOptions("knowledge_category", controller.signal),
    ])
      .then(([items, optionResponse]) => {
        const requestedArticleId = articleIdFromUrl();
        const initialArticle = items.find((article) => article.id === requestedArticleId)
          ?? items[0]
          ?? null;
        setCategoryOptions(optionResponse.values);
        setArticles(items);
        setActiveId(initialArticle?.id ?? null);
        setExpandedCategories(new Set(initialArticle ? [initialArticle.category] : []));
        if (initialArticle && requestedArticleId !== initialArticle.id) {
          window.history.replaceState(null, "", articleHash(initialArticle.id));
        }
      })
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setError("暂时无法加载投资手册，请稍后重试。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    function selectArticleFromUrl() {
      const requestedArticleId = articleIdFromUrl();
      if (requestedArticleId === null) return;
      const article = articles.find((item) => item.id === requestedArticleId);
      if (!article) return;
      setActiveId(article.id);
      setInlineBodyDraft(null);
      setExpandedCategories((current) => {
        const next = new Set(current);
        next.add(article.category);
        return next;
      });
    }
    window.addEventListener("hashchange", selectArticleFromUrl);
    return () => window.removeEventListener("hashchange", selectArticleFromUrl);
  }, [articles]);

  useEffect(() => {
    if (editing === null) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [editing]);

  useEffect(() => {
    if (deleteTarget === null) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) setDeleteTarget(null);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    deleteConfirmRef.current?.focus();
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [deleteTarget, saving]);

  useEffect(() => {
    let frame: number | null = null;
    if (inlineBodyArticleId !== null) {
      frame = window.requestAnimationFrame(() => {
        const input = inlineBodyInputRef.current;
        if (!input) return;
        const maxScrollTop = Math.max(0, input.scrollHeight - input.clientHeight);
        input.scrollTop = inlineBodyScrollRatioRef.current * maxScrollTop;
      });
    } else if (restoreReaderScrollRef.current) {
      restoreReaderScrollRef.current = false;
      frame = window.requestAnimationFrame(() => {
        const reader = readerRef.current;
        if (!reader) return;
        const maxScrollTop = Math.max(0, reader.scrollHeight - reader.clientHeight);
        reader.scrollTop = inlineBodyScrollRatioRef.current * maxScrollTop;
      });
    }
    return () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, [inlineBodyArticleId]);

  const catalogCategories = useMemo(
    () => Array.from(new Set(articles.map((article) => article.category))),
    [articles],
  );
  const categories = useMemo(
    () => Array.from(new Set([...(draft.category ? [draft.category] : []), ...categoryOptions])),
    [categoryOptions, draft.category],
  );
  const filteredArticles = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return articles.filter((article) => {
      if (!normalized) return true;
      const sourceText = article.sources
        .map((source) => source.name + " " + (source.url ?? ""))
        .join(" ");
      return [
        article.title,
        article.category,
        article.contentMarkdown,
        article.tags.join(" "),
        sourceText,
      ].join(" ").toLocaleLowerCase().includes(normalized);
    });
  }, [articles, query]);
  const groupedArticles = useMemo(
    () => catalogCategories
      .map((category) => [
        category,
        filteredArticles.filter((article) => article.category === category),
      ] as const)
      .filter(([, items]) => items.length > 0),
    [catalogCategories, filteredArticles],
  );
  const canReorder = query.trim() === "" && !reordering;
  const activeArticle =
    filteredArticles.find((article) => article.id === activeId)
    ?? filteredArticles[0]
    ?? null;
  const activeArticleId = activeArticle?.id ?? null;

  useEffect(() => {
    inlineBodyScrollRatioRef.current = 0;
    restoreReaderScrollRef.current = false;
    const frame = window.requestAnimationFrame(() => {
      readerRef.current?.scrollTo({ top: 0, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeArticleId]);

  function toggleCategory(category: string) {
    setExpandedCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  function startNew() {
    setInlineBodyDraft(null);
    setEditing("new");
    setDraft(emptyDraft(categoryOptions));
    setOpenSelect(null);
    setError(null);
  }

  function startEdit(article: KnowledgeArticle) {
    setInlineBodyDraft(null);
    setEditing(article);
    setDraft(toDraft(article));
    setOpenSelect(null);
    setError(null);
  }

  function closeEditor() {
    if (!saving) {
      setEditing(null);
      setOpenSelect(null);
      setError(null);
    }
  }

  function rememberInlineBodyPosition() {
    const input = inlineBodyInputRef.current;
    const maxScrollTop = input
      ? Math.max(0, input.scrollHeight - input.clientHeight)
      : 0;
    inlineBodyScrollRatioRef.current = input && maxScrollTop > 0
      ? input.scrollTop / maxScrollTop
      : 0;
    restoreReaderScrollRef.current = true;
  }

  function updateSource(index: number, field: keyof KnowledgeSource, value: string) {
    setDraft((current) => ({
      ...current,
      sources: current.sources.map((source, sourceIndex) => (
        sourceIndex === index
          ? field === "name"
            ? { ...source, name: value }
            : { ...source, url: value || null }
          : source
      )),
    }));
  }

  async function saveArticle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const currentEditing = editing;
    if (currentEditing === null) return;
    setSaving(true);
    setError(null);
    const payload = {
      ...draft,
      title: draft.title.trim(),
      category: draft.category.trim(),
      summary: "",
      contentMarkdown: draft.contentMarkdown.trim(),
      sources: draft.sources
        .filter((source) => source.name.trim())
        .map((source) => ({
          name: source.name.trim(),
          url: source.url?.trim() || null,
        })),
    };
    try {
      const saved = currentEditing === "new"
        ? await createKnowledgeArticle(payload)
        : await updateKnowledgeArticle(currentEditing.id, payload);
      setArticles((current) => (
        currentEditing === "new"
          ? [...current, saved]
          : current.map((article) => article.id === saved.id ? saved : article)
      ));
      setActiveId(saved.id);
      if (currentEditing === "new") {
        window.history.pushState(null, "", articleHash(saved.id));
      } else {
        window.history.replaceState(null, "", articleHash(saved.id));
      }
      setExpandedCategories((current) => {
        const next = new Set(current);
        next.add(saved.category);
        return next;
      });
      setEditing(null);
      setOpenSelect(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function removeArticle(article: KnowledgeArticle) {
    setSaving(true);
    setError(null);
    try {
      await deleteKnowledgeArticle(article.id);
      const articleIndex = articles.findIndex((item) => item.id === article.id);
      const remainingArticles = articles.filter((item) => item.id !== article.id);
      const nextArticle = remainingArticles[Math.min(articleIndex, remainingArticles.length - 1)] ?? null;
      setArticles(remainingArticles);
      setActiveId(nextArticle?.id ?? null);
      window.history.replaceState(
        null,
        "",
        nextArticle ? articleHash(nextArticle.id) : "#knowledge",
      );
      setInlineBodyDraft(null);
      setDeleteTarget(null);
    } catch {
      setError("删除失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function saveInlineBody(article: KnowledgeArticle) {
    if (inlineBodyDraft?.articleId !== article.id) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await updateKnowledgeArticle(article.id, {
        title: article.title,
        category: article.category,
        summary: "",
        contentMarkdown: inlineBodyDraft.content.trim(),
        tags: article.tags,
        sources: article.sources,
        reviewedAt: article.reviewedAt,
      });
      setArticles((current) => current.map((item) => (
        item.id === saved.id ? saved : item
      )));
      rememberInlineBodyPosition();
      setInlineBodyDraft(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "正文保存失败，请重试。");
    } finally {
      setSaving(false);
    }
  }

  function beginDrag(event: DragEvent<HTMLElement>, item: DragItem) {
    if (!canReorder) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", JSON.stringify(item));
    setDragItem(item);
    setDropTarget(null);
  }

  function finishDrag() {
    setDragItem(null);
    setDropTarget(null);
  }

  function pointerPosition(event: DragEvent<HTMLElement>): "before" | "after" {
    const bounds = event.currentTarget.getBoundingClientRect();
    return event.clientY < bounds.top + bounds.height / 2 ? "before" : "after";
  }

  async function persistOrder(groups: KnowledgeCategoryOrder[]) {
    const previous = articles;
    const byId = new Map(previous.map((article) => [article.id, article]));
    const optimistic = groups.flatMap((group, categoryOrder) => (
      group.articleIds.map((articleId, articleOrder) => ({
        ...byId.get(articleId)!,
        category: group.category,
        categoryOrder,
        articleOrder,
      }))
    ));
    setArticles(optimistic);
    setReordering(true);
    setError(null);
    try {
      setArticles(await reorderKnowledgeArticles(groups));
    } catch (reason) {
      setArticles(previous);
      setError(reason instanceof Error ? reason.message : "目录排序保存失败，请重试。");
    } finally {
      setReordering(false);
      finishDrag();
    }
  }

  function moveCategory(targetCategory: string, position: "before" | "after") {
    if (dragItem?.type !== "category" || dragItem.category === targetCategory) return;
    const groups = orderGroups(articles).map((group) => ({
      ...group,
      articleIds: [...group.articleIds],
    }));
    const sourceIndex = groups.findIndex((group) => group.category === dragItem.category);
    if (sourceIndex < 0) return;
    const [moved] = groups.splice(sourceIndex, 1);
    const targetIndex = groups.findIndex((group) => group.category === targetCategory);
    if (targetIndex < 0) return;
    groups.splice(targetIndex + (position === "after" ? 1 : 0), 0, moved);
    void persistOrder(groups);
  }

  function moveArticle(
    targetCategory: string,
    targetArticleId: number | null,
    position: "before" | "after" = "after",
  ) {
    if (dragItem?.type !== "article" || dragItem.articleId === targetArticleId) return;
    const groups = orderGroups(articles).map((group) => ({
      ...group,
      articleIds: [...group.articleIds],
    }));
    const sourceGroupIndex = groups.findIndex((group) => (
      group.articleIds.includes(dragItem.articleId)
    ));
    if (sourceGroupIndex < 0) return;
    groups[sourceGroupIndex].articleIds = groups[sourceGroupIndex].articleIds.filter(
      (articleId) => articleId !== dragItem.articleId,
    );
    if (groups[sourceGroupIndex].articleIds.length === 0) groups.splice(sourceGroupIndex, 1);

    let targetGroup = groups.find((group) => group.category === targetCategory);
    if (!targetGroup) {
      targetGroup = { category: targetCategory, articleIds: [] };
      groups.push(targetGroup);
    }
    if (targetArticleId === null) {
      targetGroup.articleIds.push(dragItem.articleId);
    } else {
      const targetIndex = targetGroup.articleIds.indexOf(targetArticleId);
      targetGroup.articleIds.splice(
        Math.max(0, targetIndex) + (position === "after" ? 1 : 0),
        0,
        dragItem.articleId,
      );
    }
    void persistOrder(groups);
  }

  function allowDrop(event: DragEvent<HTMLElement>) {
    if (!canReorder || dragItem === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }

  return (
    <main className="knowledge-page">
      <section className="knowledge-workspace page-width" aria-labelledby="knowledge-title">
        <header className="knowledge-heading">
          <div>
            <span className="section-kicker">长期有效的基础知识</span>
            <h1 id="knowledge-title">投资手册</h1>
          </div>
          <div className="knowledge-heading-actions">
            <button className="knowledge-new-button" type="button" onClick={startNew}>
              ＋ 新建文章
            </button>
            <button className="content-options-button" type="button" onClick={() => setManagingCategories(true)} aria-label="管理投资手册" title="管理投资手册">
              <SettingsIcon />
            </button>
          </div>
        </header>

        <div className="knowledge-toolbar">
          <label className="knowledge-search">
            <SearchIcon />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索主题、正文、标签或来源"
            />
          </label>
        </div>

        <div className="knowledge-layout">
          <aside className="knowledge-sidebar" aria-label="手册目录">
            <div className="knowledge-sidebar-summary">
              <span>主题目录</span>
              <strong>{filteredArticles.length}</strong>
            </div>
            <div className="knowledge-catalog">
              {groupedArticles.map(([category, items]) => (
                <section
                  className={
                    dropTarget?.type === "category" && dropTarget.category === category
                      ? `drop-${dropTarget.position}`
                      : ""
                  }
                  key={category}
                >
                  <div
                    className={
                      dropTarget?.type === "category-content"
                        && dropTarget.category === category
                        ? "knowledge-category-header drop-content"
                        : "knowledge-category-header"
                    }
                    onDragOver={(event) => {
                      allowDrop(event);
                      if (dragItem?.type === "category") {
                        setDropTarget({
                          type: "category",
                          category,
                          position: pointerPosition(event),
                        });
                      } else if (dragItem?.type === "article") {
                        setDropTarget({ type: "category-content", category });
                      }
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (dragItem?.type === "category") {
                        moveCategory(category, pointerPosition(event));
                      } else if (dragItem?.type === "article") {
                        moveArticle(category, null);
                      }
                    }}
                  >
                    <h2>
                      <button
                        className="knowledge-category-toggle"
                        type="button"
                        aria-expanded={query.trim() !== "" || expandedCategories.has(category)}
                        onClick={() => toggleCategory(category)}
                      >
                        <span className="knowledge-category-chevron" aria-hidden="true">{query.trim() !== "" || expandedCategories.has(category) ? "−" : "+"}</span>
                        <span>{category}</span>
                      </button>
                    </h2>
                    <button
                      className="knowledge-drag-handle"
                      type="button"
                      draggable={canReorder}
                      aria-label={`拖动主题“${category}”`}
                      aria-disabled={!canReorder}
                      title={canReorder ? "拖动调整主题顺序" : "清除搜索后可调整顺序"}
                      onDragStart={(event) => beginDrag(event, { type: "category", category })}
                      onDragEnd={finishDrag}
                    >
                      <span aria-hidden="true">⠿</span>
                    </button>
                  </div>
                  {(query.trim() !== "" || expandedCategories.has(category)) && items.map((article) => (
                    <div
                      key={article.id}
                      className={[
                        "knowledge-article-row",
                        activeArticle?.id === article.id ? "active" : "",
                        dropTarget?.type === "article"
                          && dropTarget.articleId === article.id
                          ? `drop-${dropTarget.position}`
                          : "",
                      ].filter(Boolean).join(" ")}
                      onDragOver={(event) => {
                        if (dragItem?.type !== "article") return;
                        allowDrop(event);
                        setDropTarget({
                          type: "article",
                          articleId: article.id,
                          position: pointerPosition(event),
                        });
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        if (dragItem?.type !== "article") return;
                        moveArticle(category, article.id, pointerPosition(event));
                      }}
                    >
                      <button
                        className="knowledge-article-select"
                        type="button"
                        onClick={() => {
                          setActiveId(article.id);
                          if (window.location.hash !== articleHash(article.id)) {
                            window.history.pushState(null, "", articleHash(article.id));
                          }
                          setInlineBodyDraft(null);
                          setExpandedCategories((current) => {
                            const next = new Set(current);
                            next.add(category);
                            return next;
                          });
                        }}
                      >
                        <strong>{article.title}</strong>
                      </button>
                      <button
                        className="knowledge-drag-handle"
                        type="button"
                        draggable={canReorder}
                        aria-label={`拖动文章“${article.title}”`}
                        aria-disabled={!canReorder}
                        title={canReorder ? "拖动调整文章顺序或更换主题" : "清除搜索后可调整顺序"}
                        onDragStart={(event) => beginDrag(event, {
                          type: "article",
                          articleId: article.id,
                        })}
                        onDragEnd={finishDrag}
                      >
                        <span aria-hidden="true">⠿</span>
                      </button>
                    </div>
                  ))}
                </section>
              ))}
              {!loading && filteredArticles.length === 0 && (
                <p className="knowledge-empty-list">没有匹配的文章</p>
              )}
            </div>
          </aside>

          <div className="knowledge-reader-shell">
          <article
            ref={readerRef}
            className="knowledge-reader"
            onScroll={(event) => setShowScrollTop(event.currentTarget.scrollTop > 160)}
          >
            {loading ? (
              <div className="knowledge-empty-state">
                <span className="spinner" />
                <p>正在加载投资手册…</p>
              </div>
            ) : activeArticle ? (
              <>
                <header className="knowledge-reader-head">
                  <h2>{activeArticle.title}</h2>
                  <div className="knowledge-reader-actions">
                    <button
                      className={inlineBodyDraft?.articleId === activeArticle.id ? "primary" : ""}
                      type="button"
                      disabled={saving}
                      onClick={() => {
                        if (inlineBodyDraft?.articleId === activeArticle.id) {
                          void saveInlineBody(activeArticle);
                        } else {
                          const reader = readerRef.current;
                          const maxScrollTop = reader
                            ? Math.max(0, reader.scrollHeight - reader.clientHeight)
                            : 0;
                          inlineBodyScrollRatioRef.current = reader && maxScrollTop > 0
                            ? reader.scrollTop / maxScrollTop
                            : 0;
                          setInlineBodyDraft({
                            articleId: activeArticle.id,
                            content: activeArticle.contentMarkdown,
                          });
                          setError(null);
                        }
                      }}
                    >
                      {inlineBodyDraft?.articleId === activeArticle.id
                        ? saving ? "保存中…" : "保存正文"
                        : "编辑正文"}
                    </button>
                    {inlineBodyDraft?.articleId === activeArticle.id && (
                      <button
                        className="cancel"
                        type="button"
                        disabled={saving}
                        onClick={() => {
                          rememberInlineBodyPosition();
                          setInlineBodyDraft(null);
                        }}
                      >
                        取消保存
                      </button>
                    )}
                    {inlineBodyDraft?.articleId !== activeArticle.id && (
                      <>
                        <button
                          type="button"
                          disabled={saving}
                          onClick={() => startEdit(activeArticle)}
                        >
                          编辑
                        </button>
                        <button
                          className="danger"
                          type="button"
                          disabled={saving}
                          onClick={() => {
                            setError(null);
                            setDeleteTarget(activeArticle);
                          }}
                        >
                          删除
                        </button>
                      </>
                    )}
                  </div>
                </header>
                {error && editing === null && (
                  <p className="knowledge-error knowledge-reader-error" role="alert">{error}</p>
                )}
                {inlineBodyDraft?.articleId === activeArticle.id ? (
                  <div className="knowledge-inline-editor">
                    <textarea
                      ref={inlineBodyInputRef}
                      autoFocus
                      aria-label="Markdown 正文源码"
                      value={inlineBodyDraft.content}
                      onChange={(event) => setInlineBodyDraft({
                        articleId: activeArticle.id,
                        content: event.target.value,
                      })}
                    />
                  </div>
                ) : (
                  <div className="knowledge-reader-grid">
                    <div className="knowledge-reader-main">
                      {activeArticle.tags.length > 0 && (
                        <div className="knowledge-tags">
                          {activeArticle.tags.map((tag) => <span key={tag}>#{tag}</span>)}
                        </div>
                      )}
                      <div className="knowledge-body-card">
                        <MarkdownRenderer content={activeArticle.contentMarkdown} emptyText="暂未填写正文。" />
                      </div>
                      {activeArticle.sources.length > 0 && (
                        <section className="knowledge-sources">
                          <h3>参考资料</h3>
                          {activeArticle.sources.map((source) => (
                            <div key={source.name + "-" + (source.url ?? "")}>
                              <span>{source.name}</span>
                              {source.url && (
                                <a href={source.url} target="_blank" rel="noreferrer">打开来源 ↗</a>
                              )}
                            </div>
                          ))}
                        </section>
                      )}
                    </div>
                    <MarkdownToc key={activeArticle.id} content={activeArticle.contentMarkdown} />
                  </div>
                )}
              </>
            ) : (
              <>
                {error && editing === null && (
                  <p className="knowledge-error" role="alert">{error}</p>
                )}
                <div className="knowledge-empty-state">
                  <strong>建立你的第一篇基础知识</strong>
                  <p>把利率、黄金、债券和资产配置中的稳定结论整理成可复用的文章。</p>
                  <button type="button" onClick={startNew}>新建第一篇文章</button>
                </div>
              </>
            )}
          </article>
          {inlineBodyArticleId === null && (
            <button
              className={`knowledge-scroll-top${showScrollTop ? " visible" : ""}`}
              type="button"
              aria-label="滚动到顶部"
              title="滚动到顶部"
              onClick={() => readerRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
            >
              <ArrowUpIcon />
            </button>
          )}
          </div>
        </div>
      </section>

      {editing !== null && (
        <div
          className="knowledge-editor-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeEditor();
          }}
        >
          <div
            className="knowledge-editor-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="knowledge-editor-title"
          >
            <form onSubmit={saveArticle}>
              <header className="knowledge-editor-head">
                <div>
                  <span className="section-kicker">知识库维护</span>
                  <h2 id="knowledge-editor-title">
                    {editing === "new" ? "新建手册文章" : "编辑手册文章"}
                  </h2>
                </div>
                <button
                  className="icon-button"
                  type="button"
                  disabled={saving}
                  onClick={closeEditor}
                  aria-label="关闭"
                >
                  <CloseIcon />
                </button>
              </header>
              {error && (
                <p className="knowledge-error knowledge-editor-error" role="alert">{error}</p>
              )}
              <div className="knowledge-form-grid">
                <label>
                  <span>标题</span>
                  <input
                    required
                    maxLength={200}
                    value={draft.title}
                    onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                  />
                </label>
                <label>
                  <span>分类</span>
                  <NoteSelect
                    id="knowledge-category"
                    value={draft.category}
                    options={categories.map((item) => [item, item] as const)}
                    open={openSelect === "category"}
                    onOpenChange={(open) => setOpenSelect(open ? "category" : null)}
                    onChange={(value) => setDraft({ ...draft, category: value })}
                  />
                </label>
                <label>
                  <span>标签</span>
                  <input
                    value={draft.tags.join("、")}
                    onChange={(event) => setDraft({
                      ...draft,
                      tags: splitTags(event.target.value),
                    })}
                    placeholder="利率、资产配置、风险"
                  />
                </label>
              </div>
              <label className="knowledge-form-field">
                <span>正文（Markdown）</span>
                <textarea
                  className="knowledge-content-input"
                  required
                  rows={14}
                  value={draft.contentMarkdown}
                  onChange={(event) => setDraft({
                    ...draft,
                    contentMarkdown: event.target.value,
                  })}
                  placeholder={"# 主题\n\n写下定义、逻辑、适用场景和注意事项。"}
                />
              </label>
              <div className="knowledge-form-field">
                <div className="knowledge-field-heading">
                  <span>参考资料</span>
                </div>
                <div className="knowledge-source-editor">
                  {draft.sources.map((source, index) => (
                    <div className="knowledge-source-row" key={String(index)}>
                      <input
                        value={source.name}
                        onChange={(event) => updateSource(index, "name", event.target.value)}
                        placeholder="资料名称"
                      />
                      <input
                        value={source.url ?? ""}
                        onChange={(event) => updateSource(index, "url", event.target.value)}
                        placeholder="https://…"
                      />
                      <div className="knowledge-source-actions">
                        {draft.sources.length > 1 && (
                          <button
                            className="knowledge-remove-source"
                            type="button"
                            onClick={() => setDraft((current) => ({
                              ...current,
                              sources: current.sources.filter(
                                (_, sourceIndex) => sourceIndex !== index,
                              ),
                            }))}
                            aria-label="删除资料"
                          >
                            ×
                          </button>
                        )}
                        {index === draft.sources.length - 1 && (
                          <button
                            className="knowledge-add-source"
                            type="button"
                            aria-label="添加资料"
                            title="添加资料"
                            onClick={() => setDraft((current) => ({
                              ...current,
                              sources: [...current.sources, { name: "", url: null }],
                            }))}
                          >
                            ＋
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <footer className="knowledge-editor-actions">
                <button type="button" disabled={saving} onClick={closeEditor}>取消</button>
                <button className="primary" type="submit" disabled={saving}>
                  {saving ? "保存中…" : "保存文章"}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {managingCategories && (
        <ContentOptionDialog
          pageTitle="投资手册"
          itemLabel="分类"
          values={categoryOptions}
          onClose={() => setManagingCategories(false)}
          onSave={async (values) => {
            const response = await updateContentOptions("knowledge_category", values);
            setCategoryOptions(response.values);
          }}
        />
      )}

      {deleteTarget !== null && (
        <div className="note-delete-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !saving) setDeleteTarget(null);
        }}>
          <section
            className="note-delete-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="knowledge-delete-title"
            aria-describedby="knowledge-delete-description"
          >
            <span className="section-kicker">删除文章</span>
            <h2 id="knowledge-delete-title">确认删除？</h2>
            <p id="knowledge-delete-description">
              确认删除“{deleteTarget.title}”吗？删除后无法恢复。
            </p>
            {error && <p className="note-delete-error" role="alert">{error}</p>}
            <div className="note-delete-actions">
              <button type="button" disabled={saving} onClick={() => setDeleteTarget(null)}>
                取消
              </button>
              <button
                ref={deleteConfirmRef}
                className="danger"
                type="button"
                disabled={saving}
                onClick={() => void removeArticle(deleteTarget)}
              >
                {saving ? "删除中…" : "确认删除"}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
