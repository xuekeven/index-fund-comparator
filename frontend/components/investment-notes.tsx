"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  createInvestmentNote,
  deleteInvestmentNote,
  getInvestmentNotes,
  updateInvestmentNote,
} from "@/lib/api";
import type {
  InvestmentNote,
  InvestmentNoteAction,
  InvestmentNoteCategory,
  InvestmentNotePayload,
} from "@/lib/types";
import { SearchIcon } from "./icons";

const CATEGORY_OPTIONS: InvestmentNoteCategory[] = ["长期", "实时"];
const ACTION_OPTIONS: InvestmentNoteAction[] = ["加仓", "减仓", "清仓", "持有", "观察"];
const SOURCE_OPTIONS = ["自我总结", "教主-群聊", "教主-微博", "猫笔刀-日报", "仓鼠投资-微博"] as const;

type NoteDraft = Omit<InvestmentNotePayload, "tags" | "indexIds" | "fundCodes"> & {
  tags: string;
};

function today() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" });
}

function emptyDraft(): NoteDraft {
  return {
    noteDate: today(), title: "", category: "长期", action: null,
    sourceName: SOURCE_OPTIONS[0], sourceUrl: "", sourceExcerpt: "", ownSummary: "",
    contentMarkdown: "", tags: "",
  };
}

function noteToDraft(note: InvestmentNote): NoteDraft {
  return {
    noteDate: note.noteDate,
    title: note.title,
    category: note.category,
    action: note.action,
    sourceName: note.sourceName ?? "",
    sourceUrl: note.sourceUrl ?? "",
    sourceExcerpt: note.sourceExcerpt ?? "",
    ownSummary: note.ownSummary ?? "",
    contentMarkdown: note.contentMarkdown,
    tags: note.tags.join("、"),
  };
}

function splitValues(value: string) {
  return Array.from(new Set(
    value.split(/[、,，\s]+/).map((item) => item.trim()).filter(Boolean),
  ));
}

function draftToPayload(draft: NoteDraft): InvestmentNotePayload {
  const optional = (value: string | null) => value?.trim() || null;
  return {
    ...draft,
    title: draft.title.trim(),
    sourceName: optional(draft.sourceName),
    sourceUrl: optional(draft.sourceUrl),
    sourceExcerpt: optional(draft.sourceExcerpt),
    ownSummary: draft.sourceName === "自我总结" ? null : optional(draft.ownSummary),
    contentMarkdown: draft.contentMarkdown.trim(),
    tags: splitValues(draft.tags),
    indexIds: [],
    fundCodes: [],
  };
}

function formatNoteDate(value: string) {
  const [year, month, day] = value.split("-");
  return { year, short: month + "-" + day, full: year + "年" + month + "月" + day + "日" };
}

function NoteText({ text }: { text: string }) {
  const normalized = text.trim();
  if (!normalized) return null;
  const lines = normalized.split(/\r?\n/);
  return (
    <div className="note-text">
      {lines.map((line, index) => {
        const content = line.trim();
        const heading = content.match(/^(#{1,3})\s+(.+)$/);
        const key = content + "-" + index;
        if (!content) return <span className="note-text-break" aria-hidden="true" key={key} />;
        if (heading) {
          const level = heading[1].length;
          if (level === 1) return <h3 className="note-text-heading level-1" key={key}>{heading[2]}</h3>;
          if (level === 2) return <h4 className="note-text-heading level-2" key={key}>{heading[2]}</h4>;
          return <h5 className="note-text-heading level-3" key={key}>{heading[2]}</h5>;
        }
        return content.startsWith("- ") ? (
          <p className="note-bullet" key={key}>{content.slice(2)}</p>
        ) : (
          <p key={key}>{content}</p>
        );
      })}
    </div>
  );
}

type NoteSelectProps = {
  id: string;
  label?: string;
  value: string;
  options: ReadonlyArray<readonly [string, string]>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (value: string) => void;
};

function NoteSelect({ id, label, value, options, open, onOpenChange, onChange }: NoteSelectProps) {
  const selectedLabel = options.find(([optionValue]) => optionValue === value)?.[1] ?? value;
  return (
    <div className={`multi-filter note-select ${open ? "open" : ""}`}>
      <button className="multi-filter-trigger" type="button" aria-expanded={open} aria-controls={`${id}-menu`} onClick={() => onOpenChange(!open)}>
        {label && <span>{label}</span>}
        <strong>{selectedLabel}</strong>
      </button>
      {open && (
        <div className="multi-filter-menu" id={`${id}-menu`}>
          {options.map(([optionValue, optionLabel]) => (
            <button key={optionValue || "empty"} type="button" className={value === optionValue ? "active" : ""} onClick={() => { onChange(optionValue); onOpenChange(false); }}>
              {optionLabel}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

type NoteDateFieldProps = {
  value: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (value: string) => void;
};

function NoteDateField({ value, open, onOpenChange, onChange }: NoteDateFieldProps) {
  const [cursor, setCursor] = useState(() => /^\d{4}-\d{2}/.test(value) ? value.slice(0, 7) : today().slice(0, 7));

  const [cursorYear, cursorMonth] = cursor.split("-").map(Number);
  const leadingDays = new Date(cursorYear, cursorMonth - 1, 1).getDay();
  const dayCount = new Date(cursorYear, cursorMonth, 0).getDate();
  const days = [...Array.from({ length: leadingDays }, () => null), ...Array.from({ length: dayCount }, (_, index) => index + 1)];

  function moveMonth(offset: number) {
    const next = new Date(cursorYear, cursorMonth - 1 + offset, 1);
    setCursor(next.getFullYear() + "-" + String(next.getMonth() + 1).padStart(2, "0"));
  }

  function selectDay(day: number) {
    onChange(cursor + "-" + String(day).padStart(2, "0"));
    onOpenChange(false);
  }

  return (
    <div className={`note-date-control ${open ? "open" : ""}`}>
      <input className="note-date-field" type="text" inputMode="numeric" required pattern="\d{4}-\d{2}-\d{2}" maxLength={10} value={value} onChange={(event) => onChange(event.target.value)} placeholder="YYYY-MM-DD" />
      <button className="note-calendar-trigger" type="button" aria-label="选择日期" aria-expanded={open} onClick={() => {
        if (!open && /^\d{4}-\d{2}/.test(value)) setCursor(value.slice(0, 7));
        onOpenChange(!open);
      }}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3M17 3v3M4.5 9h15M6 5h12a2 2 0 0 1 2 2v12H4V7a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
      </button>
      {open && (
        <div className="note-calendar">
          <header>
            <button type="button" aria-label="上个月" onClick={() => moveMonth(-1)}>‹</button>
            <strong>{cursorYear}年{String(cursorMonth).padStart(2, "0")}月</strong>
            <button type="button" aria-label="下个月" onClick={() => moveMonth(1)}>›</button>
          </header>
          <div className="note-calendar-week">{["日", "一", "二", "三", "四", "五", "六"].map((item) => <span key={item}>{item}</span>)}</div>
          <div className="note-calendar-days">
            {days.map((day, index) => day ? (
              <button key={day} className={value === cursor + "-" + String(day).padStart(2, "0") ? "active" : ""} type="button" onClick={() => selectDay(day)}>{day}</button>
            ) : <i key={"empty-" + index} />)}
          </div>
          <footer><button type="button" onClick={() => { onChange(today()); onOpenChange(false); }}>今天</button></footer>
        </div>
      )}
    </div>
  );
}

type NoteReaderProps = {
  note: InvestmentNote;
  active: boolean;
  saving: boolean;
  onEdit: (note: InvestmentNote) => void;
  onDelete: (note: InvestmentNote) => void;
};

function NoteReader({ note, active, saving, onEdit, onDelete }: NoteReaderProps) {
  return (
    <section id={`note-reader-${note.id}`} className={`note-reader ${active ? "active" : ""}`}>
      <header className="note-reader-head">
        <div>
          <div className="note-meta-line">
            <span>{formatNoteDate(note.noteDate).full}</span>
            {note.sourceName && (
              <span className="note-meta-source">
                {note.sourceUrl ? <a href={note.sourceUrl} target="_blank" rel="noreferrer">{note.sourceName}</a> : <strong>{note.sourceName}</strong>}
              </span>
            )}
            {note.action && <i className="action">{note.action}</i>}
          </div>
          <div className="note-title-row">
            <h2><mark>{note.title}</mark></h2>
            {note.tags.length > 0 && <div className="note-relations note-title-tags">{note.tags.map((tag) => <span key={"tag-" + tag}>#{tag}</span>)}</div>}
          </div>
        </div>
        <div className="note-reader-actions">
          <button type="button" onClick={() => onEdit(note)}>编辑</button>
          <button className="danger" type="button" disabled={saving} onClick={() => onDelete(note)}>删除</button>
        </div>
      </header>
      {note.sourceExcerpt && <section className="note-opinion-card"><span>观点归纳</span><NoteText text={note.sourceExcerpt} /></section>}
      {note.sourceName !== "自我总结" && note.ownSummary && <section className="note-summary-card"><span>自我总结</span><NoteText text={note.ownSummary} /></section>}
      {note.contentMarkdown && <section className="note-body-card"><h3>观察计划</h3><NoteText text={note.contentMarkdown} /></section>}
    </section>
  );
}

export function InvestmentNotes() {
  const [notes, setNotes] = useState<InvestmentNote[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<InvestmentNoteCategory>("长期");
  const [year, setYear] = useState("全部");
  const [source, setSource] = useState("全部");
  const [openSelect, setOpenSelect] = useState<string | null>(null);
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InvestmentNote | null>(null);
  const [pendingScrollId, setPendingScrollId] = useState<number | null>(null);
  const [draft, setDraft] = useState<NoteDraft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deleteConfirmRef = useRef<HTMLButtonElement>(null);
  const notePanelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    getInvestmentNotes(controller.signal)
      .then((items) => {
        setNotes(items);
        setActiveId((current) => current ?? items[0]?.id ?? null);
        setError(null);
      })
      .catch((requestError) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        setError("暂时无法加载投资笔记，请稍后重试。");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!openSelect) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest(".note-select, .note-date-control")) return;
      setOpenSelect(null);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, [openSelect]);

  useEffect(() => {
    if (editing === null) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) {
        setEditing(null);
        setOpenSelect(null);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [editing, saving]);

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

  const years = useMemo(
    () => Array.from(new Set(notes.map((note) => note.noteDate.slice(0, 4)))).sort().reverse(),
    [notes],
  );
  const sources = useMemo(
    () => Array.from(new Set(
      notes.map((note) => note.sourceName).filter((value): value is string => Boolean(value)),
    )).sort((left, right) => left.localeCompare(right, "zh-CN")),
    [notes],
  );

  const filteredNotes = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
    return notes.filter((note) => {
      if (note.category !== category) return false;
      if (year !== "全部" && !note.noteDate.startsWith(year)) return false;
      if (source !== "全部" && note.sourceName !== source) return false;
      if (!normalizedQuery) return true;
      const searchable = [
        note.title, note.sourceName, note.sourceExcerpt, note.ownSummary,
        note.contentMarkdown, ...note.tags,
      ].filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
      return searchable.includes(normalizedQuery);
    });
  }, [category, notes, query, source, year]);

  const groupedNotes = useMemo(() => {
    const groups = new Map<string, InvestmentNote[]>();
    filteredNotes.forEach((note) => {
      const noteYear = note.noteDate.slice(0, 4);
      groups.set(noteYear, [...(groups.get(noteYear) ?? []), note]);
    });
    return Array.from(groups.entries());
  }, [filteredNotes]);

  const activeNote = filteredNotes.find((note) => note.id === activeId)
    ?? filteredNotes[0] ?? null;

  useEffect(() => {
    if (pendingScrollId === null || editing !== null) return;
    const frame = window.requestAnimationFrame(() => {
      const reader = document.getElementById(`note-reader-${pendingScrollId}`);
      if (!reader) return;
      reader.scrollIntoView({ behavior: "smooth", block: "start" });
      document.getElementById(`note-timeline-${pendingScrollId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      setPendingScrollId(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [editing, filteredNotes, pendingScrollId]);

  useEffect(() => {
    const panel = notePanelRef.current;
    if (!panel || filteredNotes.length === 0) return;
    let frame = 0;

    const syncActiveNote = () => {
      frame = 0;
      const panelTop = panel.getBoundingClientRect().top;
      const activationLine = panelTop + Math.min(100, panel.clientHeight * 0.2);
      let nextId = filteredNotes[0].id;

      for (const note of filteredNotes) {
        const reader = document.getElementById(`note-reader-${note.id}`);
        if (!reader || reader.getBoundingClientRect().top > activationLine) break;
        nextId = note.id;
      }
      if (panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 2) {
        nextId = filteredNotes[filteredNotes.length - 1].id;
      }

      setActiveId((current) => current === nextId ? current : nextId);
      document.getElementById(`note-timeline-${nextId}`)
        ?.scrollIntoView({ block: "nearest" });
    };

    const scheduleSync = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(syncActiveNote);
    };

    panel.addEventListener("scroll", scheduleSync, { passive: true });
    scheduleSync();
    return () => {
      panel.removeEventListener("scroll", scheduleSync);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [filteredNotes]);

  function startNew() {
    setDraft(emptyDraft()); setEditing("new"); setOpenSelect(null); setError(null);
  }

  function startEdit(note: InvestmentNote) {
    setDraft(noteToDraft(note)); setEditing(note.id); setOpenSelect(null); setError(null);
  }

  async function saveNote(event: FormEvent) {
    event.preventDefault();
    const payload = draftToPayload(draft);
    if (!payload.title) { setError("请填写笔记标题。"); return; }
    const isNewNote = editing === "new";
    setSaving(true); setError(null);
    try {
      const saved = isNewNote
        ? await createInvestmentNote(payload)
        : await updateInvestmentNote(editing as number, payload);
      setNotes((current) => [
        saved, ...current.filter((note) => note.id !== saved.id),
      ].sort((left, right) => right.noteDate.localeCompare(left.noteDate) || right.id - left.id));
      setActiveId(saved.id); setEditing(null);
      if (isNewNote) {
        setCategory(saved.category);
        setYear("全部");
        setSource("全部");
        setQuery("");
        setPendingScrollId(saved.id);
      }
    } catch {
      setError("保存失败，请检查数据服务后重试。");
    } finally { setSaving(false); }
  }

  async function removeNote(note: InvestmentNote) {
    setSaving(true); setError(null);
    try {
      await deleteInvestmentNote(note.id);
      setNotes((current) => current.filter((item) => item.id !== note.id));
      setActiveId(null); setEditing(null); setDeleteTarget(null);
    } catch {
      setError("删除失败，请稍后重试。");
    } finally { setSaving(false); }
  }

  return (
    <main className="notes-page">
      <section className="notes-workspace page-width" aria-labelledby="notes-title">
        <header className="notes-heading">
          <div>
            <span className="section-kicker">复盘与判断</span>
            <h1 id="notes-title">投资笔记</h1>
            <p>把来源观点、自己的判断和复盘记录分开整理。</p>
          </div>
          <div className="notes-heading-actions">
            <button className="notes-new-button" type="button" onClick={startNew}>＋ 新建笔记</button>
          </div>
        </header>

        <div className="notes-toolbar">
          <div className="notes-category-filter" aria-label="笔记类型">
            {CATEGORY_OPTIONS.map((item) => (
              <button key={item} className={category === item ? "active" : ""} type="button" onClick={() => setCategory(item)}>{item}</button>
            ))}
          </div>
          <NoteSelect
            id="note-year"
            label="年份"
            value={year}
            options={[[ "全部", "全部" ] as const, ...years.map((item) => [item, item + "年"] as const)]}
            open={openSelect === "year"}
            onOpenChange={(open) => setOpenSelect(open ? "year" : null)}
            onChange={setYear}
          />
          <NoteSelect
            id="note-source-filter"
            label="来源"
            value={source}
            options={[[ "全部", "全部" ] as const, ...sources.map((item) => [item, item] as const)]}
            open={openSelect === "source-filter"}
            onOpenChange={(open) => setOpenSelect(open ? "source-filter" : null)}
            onChange={setSource}
          />
          <label className="notes-search">
            <SearchIcon />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、来源、正文或标签" />
          </label>
        </div>

        <div className="notes-layout">
          <aside className="notes-sidebar" aria-label="笔记目录">
            <div className="notes-sidebar-summary"><span>笔记目录</span><strong>{filteredNotes.length}</strong></div>
            <div className="notes-timeline">
              {groupedNotes.map(([noteYear, items]) => (
                <section key={noteYear}>
                  <h2>{noteYear}</h2>
                  {items.map((note) => {
                    const formatted = formatNoteDate(note.noteDate);
                    return (
                      <button id={`note-timeline-${note.id}`} key={note.id} className={activeNote?.id === note.id ? "active" : ""} type="button" onClick={() => {
                          setActiveId(note.id); setEditing(null); setError(null);
                          window.requestAnimationFrame(() => document.getElementById("note-reader-" + note.id)?.scrollIntoView({ behavior: "smooth", block: "start" }));
                        }}>
                        <span>{formatted.short}</span><strong>{note.title}</strong>
                      </button>
                    );
                  })}
                </section>
              ))}
              {!loading && filteredNotes.length === 0 && <p className="notes-empty-list">没有匹配的笔记</p>}
            </div>
          </aside>

          <article ref={notePanelRef} className="note-panel">
            {error && editing === null && <p className="notes-error" role="alert">{error}</p>}
            {loading ? (
              <div className="note-empty-state"><span className="spinner" /><p>正在加载笔记…</p></div>
            ) : filteredNotes.length > 0 ? (
              <div className="note-reader-list">
                {filteredNotes.map((note) => (
                  <NoteReader
                    key={note.id}
                    note={note}
                    active={activeNote?.id === note.id}
                    saving={saving}
                    onEdit={startEdit}
                    onDelete={(item) => { setDeleteTarget(item); setError(null); }}
                  />
                ))}
              </div>
            ) : (
              <div className="note-empty-state"><strong>开始记录你的投资判断</strong><p>把别人的观点、自己的总结和复盘记录分开保存，方便以后回看。</p><button type="button" onClick={startNew}>新建第一篇笔记</button></div>
            )}
          </article>
        </div>
      </section>

      {editing !== null && (
        <div className="note-editor-overlay" role="presentation" onMouseDown={(event) => {
            if (event.target === event.currentTarget && !saving) {
              setEditing(null);
              setOpenSelect(null);
            }
          }}>
            <div className="note-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="note-editor-title">
              <form className="note-editor" onSubmit={saveNote}>
                <div className="note-editor-head">
                  <div><span className="section-kicker">{editing === "new" ? "创建记录" : "修改记录"}</span><h2 id="note-editor-title">{editing === "new" ? "新建投资笔记" : "编辑投资笔记"}</h2></div>
                  <button type="button" disabled={saving} onClick={() => { setEditing(null); setOpenSelect(null); }}>取消</button>
                </div>
                {error && <p className="notes-error note-editor-error" role="alert">{error}</p>}
                <div className="note-form-grid">
                  <div className="note-form-control"><span>日期</span><NoteDateField value={draft.noteDate} open={openSelect === "date"} onOpenChange={(open) => setOpenSelect(open ? "date" : null)} onChange={(value) => setDraft({ ...draft, noteDate: value })} /></div>
                  <label><span>标题</span><input required maxLength={200} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="例如：07-21 加减仓" /></label>
                  <div className="note-form-control"><span>类型</span><NoteSelect id="note-category" value={draft.category} options={CATEGORY_OPTIONS.map((item) => [item, item] as const)} open={openSelect === "category"} onOpenChange={(open) => setOpenSelect(open ? "category" : null)} onChange={(value) => setDraft({ ...draft, category: value as InvestmentNoteCategory })} /></div>
                  <div className="note-form-control"><span>行动观点</span><NoteSelect id="note-action" value={draft.action ?? ""} options={[[ "", "暂无" ] as const, ...ACTION_OPTIONS.map((item) => [item, item] as const)]} open={openSelect === "action"} onOpenChange={(open) => setOpenSelect(open ? "action" : null)} onChange={(value) => setDraft({ ...draft, action: value ? value as InvestmentNoteAction : null })} /></div>
                  <div className="note-form-control"><span>来源</span><NoteSelect id="note-source" value={draft.sourceName ?? ""} options={SOURCE_OPTIONS.map((item) => [item, item] as const)} open={openSelect === "source"} onOpenChange={(open) => setOpenSelect(open ? "source" : null)} onChange={(value) => setDraft({ ...draft, sourceName: value, ownSummary: value === "自我总结" ? "" : draft.ownSummary })} /></div>
                  <label><span>来源链接</span><input value={draft.sourceUrl ?? ""} onChange={(event) => setDraft({ ...draft, sourceUrl: event.target.value })} placeholder="https://…" /></label>
                </div>
                <label className="note-form-field"><span>观点归纳</span><textarea rows={3} value={draft.sourceExcerpt ?? ""} onChange={(event) => setDraft({ ...draft, sourceExcerpt: event.target.value })} placeholder="每行可用“- ”开头记录一个观点" /></label>
                {draft.sourceName !== "自我总结" && <label className="note-form-field"><span>自我总结</span><textarea rows={3} value={draft.ownSummary ?? ""} onChange={(event) => setDraft({ ...draft, ownSummary: event.target.value })} placeholder="写下自己的判断、依据和失效条件" /></label>}
                <label className="note-form-field"><span>观察计划</span><textarea rows={3} value={draft.contentMarkdown} onChange={(event) => setDraft({ ...draft, contentMarkdown: event.target.value })} placeholder="交易计划、复盘结果或后续观察…" /></label>
                <div className="note-form-grid note-form-grid-single">
                  <label><span>标签</span><input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} placeholder="QDII、风控、估值" /></label>
                </div>
                <div className="note-editor-actions"><button type="button" disabled={saving} onClick={() => { setEditing(null); setOpenSelect(null); }}>取消</button><button className="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存笔记"}</button></div>
              </form>
            </div>
        </div>
      )}

      {deleteTarget !== null && (
        <div className="note-delete-overlay" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !saving) setDeleteTarget(null);
        }}>
          <section
            className="note-delete-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="note-delete-title"
            aria-describedby="note-delete-description"
          >
            <span className="section-kicker">删除笔记</span>
            <h2 id="note-delete-title">确认删除？</h2>
            <p id="note-delete-description">
              确认删除“{deleteTarget.title}”吗？删除后无法恢复。
            </p>
            {error && <p className="note-delete-error" role="alert">{error}</p>}
            <div className="note-delete-actions">
              <button type="button" disabled={saving} onClick={() => setDeleteTarget(null)}>取消</button>
              <button
                ref={deleteConfirmRef}
                className="danger"
                type="button"
                disabled={saving}
                onClick={() => void removeNote(deleteTarget)}
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
