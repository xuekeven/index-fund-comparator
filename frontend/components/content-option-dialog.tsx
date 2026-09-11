"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { CloseIcon } from "./icons";

type ContentOptionDialogProps = {
  pageTitle: string;
  itemLabel: string;
  values: string[];
  onClose: () => void;
  onSave: (values: string[]) => Promise<void>;
};

export function ContentOptionDialog({
  pageTitle,
  itemLabel,
  values,
  onClose,
  onSave,
}: ContentOptionDialogProps) {
  const [draft, setDraft] = useState(values.length > 0 ? values : [""]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !saving) onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, saving]);

  function update(index: number, value: string) {
    setDraft((current) => current.map((item, itemIndex) => (
      itemIndex === index ? value : item
    )));
  }

  function move(index: number, offset: -1 | 1) {
    setDraft((current) => {
      const target = index + offset;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = Array.from(new Set(draft.map((value) => value.trim()).filter(Boolean)));
    if (normalized.length === 0) {
      setError(`至少保留一个${itemLabel}。`);
      return;
    }
    if (normalized.length !== draft.filter((value) => value.trim()).length) {
      setError(`${itemLabel}不能重复。`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(normalized);
      onClose();
    } catch {
      setError("保存失败，请检查数据服务后重试。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="content-option-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <section
        className="content-option-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="content-option-title"
      >
        <form onSubmit={submit}>
          <header className="content-option-head">
            <div>
              <span className="section-kicker">页面设置</span>
              <h2 id="content-option-title">{pageTitle}管理</h2>
            </div>
            <button className="icon-button" type="button" onClick={onClose} disabled={saving} aria-label="关闭">
              <CloseIcon />
            </button>
          </header>
          <p className="content-option-help">统一管理本页面使用的可配置字段。</p>
          <section className="content-option-section">
            <header className="content-option-section-head">
              <h3>{itemLabel}选项</h3>
              <p>用于新建和编辑{pageTitle}时的“{itemLabel}”字段。</p>
            </header>
            <div className="content-option-list">
            {draft.map((value, index) => (
              <div className="content-option-row" key={String(index)}>
                <input
                  autoFocus={index === 0}
                  maxLength={200}
                  value={value}
                  onChange={(event) => update(index, event.target.value)}
                  aria-label={`${itemLabel} ${index + 1}`}
                  placeholder={`请输入${itemLabel}`}
                />
                <button type="button" onClick={() => move(index, -1)} disabled={index === 0 || saving} aria-label="上移">↑</button>
                <button type="button" onClick={() => move(index, 1)} disabled={index === draft.length - 1 || saving} aria-label="下移">↓</button>
                <button className="danger" type="button" onClick={() => setDraft((current) => current.filter((_, itemIndex) => itemIndex !== index))} disabled={draft.length === 1 || saving} aria-label="删除">×</button>
              </div>
            ))}
            </div>
            <button className="content-option-add" type="button" disabled={saving} onClick={() => setDraft((current) => [...current, ""])}>＋ 添加{itemLabel}</button>
            <p className="content-option-history">修改配置只影响后续选择，历史内容中的旧值不会被修改。</p>
          </section>
          {error && <p className="content-option-error" role="alert">{error}</p>}
          <footer className="content-option-actions">
            <button type="button" disabled={saving} onClick={onClose}>取消</button>
            <button className="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存设置"}</button>
          </footer>
        </form>
      </section>
    </div>
  );
}
