"use client";

import { useEffect, useMemo, useState } from "react";
import type { DragEvent, FormEvent } from "react";

import {
  createKnowledgeArticle,
  deleteKnowledgeArticle,
  getKnowledgeArticles,
  reorderKnowledgeArticles,
  updateKnowledgeArticle,
} from "@/lib/api";
import type {
  KnowledgeArticle,
  KnowledgeArticlePayload,
  KnowledgeCategoryOrder,
  KnowledgeSource,
} from "@/lib/types";
import { CloseIcon, SearchIcon } from "./icons";
import { NoteSelect } from "./investment-notes";

const DEFAULT_CATEGORIES = ["资产配置", "利率", "债券", "黄金", "红利策略", "交易工具"];

type DragItem =
  | { type: "category"; category: string }
  | { type: "article"; articleId: number };
type DropTarget =
  | { type: "category"; category: string; position: "before" | "after" }
  | { type: "article"; articleId: number; position: "before" | "after" }
  | { type: "category-content"; category: string }
  | null;
type ArticleDraft = KnowledgeArticlePayload;

function emptyDraft(): ArticleDraft {
  return {
    title: "",
    category: DEFAULT_CATEGORIES[0],
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
    summary: article.summary,
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

function MarkdownText({ text }: { text: string }) {
  const lines = text.trim().split(/\r?\n/);
  if (!text.trim()) {
    return <p className="knowledge-empty-copy">暂未填写正文。</p>;
  }
  return (
    <div className="knowledge-markdown">
      {lines.map((line, index) => {
        const content = line.trim();
        const key = String(index) + "-" + content;
        if (!content) {
          return <span className="knowledge-markdown-break" aria-hidden="true" key={key} />;
        }
        const heading = content.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
          const level = heading[1].length;
          if (level === 1) return <h3 key={key}>{heading[2]}</h3>;
          if (level === 2) return <h4 key={key}>{heading[2]}</h4>;
          return <h5 key={key}>{heading[2]}</h5>;
        }
        if (/^[-*]\s+/.test(content)) {
          return <p className="knowledge-bullet" key={key}>{content.slice(2)}</p>;
        }
        if (/^\d+[.)]\s+/.test(content)) {
          return <p className="knowledge-numbered" key={key}>{content}</p>;
        }
        if (content.startsWith("> ")) {
          return <blockquote key={key}>{content.slice(2)}</blockquote>;
        }
        return <p key={key}>{content}</p>;
      })}
    </div>
  );
}

export function KnowledgeBase() {
  const [articles, setArticles] = useState<KnowledgeArticle[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<KnowledgeArticle | "new" | null>(null);
  const [draft, setDraft] = useState<ArticleDraft>(emptyDraft);
  const [openSelect, setOpenSelect] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [dragItem, setDragItem] = useState<DragItem | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTarget>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getKnowledgeArticles(controller.signal)
      .then((items) => {
        setArticles(items);
        setActiveId(items[0]?.id ?? null);
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

  const catalogCategories = useMemo(
    () => Array.from(new Set(articles.map((article) => article.category))),
    [articles],
  );
  const categories = useMemo(
    () => Array.from(new Set([...catalogCategories, ...DEFAULT_CATEGORIES])),
    [catalogCategories],
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
        article.summary,
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

  function startNew() {
    setEditing("new");
    setDraft(emptyDraft());
    setOpenSelect(null);
    setError(null);
  }

  function startEdit(article: KnowledgeArticle) {
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
      summary: draft.summary.trim(),
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
      setEditing(null);
      setOpenSelect(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function removeArticle(article: KnowledgeArticle) {
    if (!window.confirm("确定删除“" + article.title + "”吗？")) return;
    setSaving(true);
    setError(null);
    try {
      await deleteKnowledgeArticle(article.id);
      setArticles((current) => current.filter((item) => item.id !== article.id));
      setActiveId(null);
    } catch {
      setError("删除失败，请稍后重试。");
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
          <button className="knowledge-new-button" type="button" onClick={startNew}>
            ＋ 新建文章
          </button>
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
                    <h2>{category}</h2>
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
                  {items.map((article) => (
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
                        onClick={() => setActiveId(article.id)}
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

          <article className="knowledge-reader">
            {error && editing === null && (
              <p className="knowledge-error" role="alert">{error}</p>
            )}
            {loading ? (
              <div className="knowledge-empty-state">
                <span className="spinner" />
                <p>正在加载投资手册…</p>
              </div>
            ) : activeArticle ? (
              <>
                <header className="knowledge-reader-head">
                  <div>
                    <div className="knowledge-meta-line">
                      <span>{activeArticle.category}</span>
                    </div>
                    <h2>{activeArticle.title}</h2>
                    {activeArticle.summary && <p>{activeArticle.summary}</p>}
                  </div>
                  <div className="knowledge-reader-actions">
                    <button type="button" onClick={() => startEdit(activeArticle)}>编辑</button>
                    <button
                      className="danger"
                      type="button"
                      disabled={saving}
                      onClick={() => void removeArticle(activeArticle)}
                    >
                      删除
                    </button>
                  </div>
                </header>
                {activeArticle.tags.length > 0 && (
                  <div className="knowledge-tags">
                    {activeArticle.tags.map((tag) => <span key={tag}>#{tag}</span>)}
                  </div>
                )}
                <div className="knowledge-body-card">
                  <MarkdownText text={activeArticle.contentMarkdown} />
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
              </>
            ) : (
              <div className="knowledge-empty-state">
                <strong>建立你的第一篇基础知识</strong>
                <p>把利率、黄金、债券和资产配置中的稳定结论整理成可复用的文章。</p>
                <button type="button" onClick={startNew}>新建第一篇文章</button>
              </div>
            )}
          </article>
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
                <span>摘要</span>
                <textarea
                  rows={2}
                  value={draft.summary}
                  onChange={(event) => setDraft({ ...draft, summary: event.target.value })}
                  placeholder="用一两句话说明这篇文章解决什么问题"
                />
              </label>
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
                </div>
                <div className="knowledge-source-editor">
                  {draft.sources.map((source, index) => (
                    <div className={`knowledge-source-row ${draft.sources.length === 1 ? "single" : ""}`} key={String(index)}>
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
                      {draft.sources.length > 1 && (
                        <button
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
    </main>
  );
}
