import { useEffect, useRef } from "react";

import { CloseIcon } from "./icons";

interface ShareClassHelpDialogProps {
  onClose: () => void;
}

const SHARE_ROWS = [
  {
    shareClass: "A 类",
    fee: "通常收取申购费，通常不收销售服务费",
    fit: "持有时间较长，或申购费有较大折扣时通常更有优势",
  },
  {
    shareClass: "C 类",
    fee: "通常不收申购费，但按年计提销售服务费",
    fit: "短期或中期持有、希望减少一次性申购费时通常更合适",
  },
  {
    shareClass: "E 类",
    fee: "规则因基金而异，常见于特定渠道，销售服务费可能低于 C 类",
    fit: "应单独比较 E 类的销售服务费、申购限制和销售渠道",
  },
];

export function ShareClassHelpDialog({ onClose }: ShareClassHelpDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="comparison-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="share-class-help-title"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="sync-info-sheet share-class-help-sheet">
        <header className="comparison-header">
          <div>
            <span className="section-kicker">份额说明</span>
            <h2 id="share-class-help-title">A、C、E 份额怎么选？</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="关闭份额说明"
          >
            <CloseIcon />
          </button>
        </header>

        <div className="share-class-help-content">
          <p className="share-class-intro">
            同一基金不同份额通常投资组合相同，主要区别在收费方式、销售渠道和申购限制。页面“运作费率”包含管理费、托管费和销售服务费。
          </p>

          <div className="share-class-table-wrap">
            <table className="share-class-table">
              <thead>
                <tr>
                  <th>份额</th>
                  <th>常见收费方式</th>
                  <th>一般适合</th>
                </tr>
              </thead>
              <tbody>
                {SHARE_ROWS.map((row) => (
                  <tr key={row.shareClass}>
                    <th>{row.shareClass}</th>
                    <td>{row.fee}</td>
                    <td>{row.fit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="holding-guide">
            <h3>按持有时间判断</h3>
            <ul>
              <li><strong>短期：</strong>C 或低销售服务费的 E 类通常更省，但必须同时检查赎回费，尤其是持有不足 7 天。</li>
              <li><strong>中期：</strong>比较“A 类实际申购费”与“C/E 类每年销售服务费 × 预计持有年数”。</li>
              <li><strong>长期：</strong>A 类通常更有优势，因为一次性申购费不会逐年重复计提；若 A 类申购费无折扣，临界时间会更长。</li>
            </ul>
          </section>

          <div className="share-class-formula">
            <strong>简单临界点</strong>
            <p>预计临界持有年数 ≈ A 类实际申购费率 ÷ C/E 类相对 A 类多出的年销售服务费率。</p>
            <p>例如 A 类实际申购费 1.20%、C 类销售服务费 0.35%/年，约 3.4 年后 A 类可能更省；若申购费打一折为 0.12%，临界点约 4 个月。</p>
          </div>

          <p className="share-class-disclaimer">
            上述是常见规则，不是投资建议。不同基金的费率折扣、赎回费、最低金额和 E 类规则可能不同，请以对应基金最新产品资料概要及销售渠道为准。
          </p>
        </div>
      </div>
    </div>
  );
}
