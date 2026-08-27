import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  confirmDiscardUnsavedWork,
  hasUnsavedWork,
  registerUnsavedWorkPrompt,
  type UnsavedWorkReason,
} from "../tenant/unsavedWork";

export function UnsavedWorkDialog() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [pending, setPending] = useState<{
    reason: UnsavedWorkReason;
    resolve: (discard: boolean) => void;
  } | null>(null);

  useEffect(() => {
    registerUnsavedWorkPrompt(
      (reason) =>
        new Promise((resolve) => {
          setPending({ reason, resolve });
        }),
    );
    return () => {
      registerUnsavedWorkPrompt(null);
    };
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      if (!hasUnsavedWork()) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      if (target.closest("button, [role='button']")) {
        return;
      }
      const anchor = target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) {
        return;
      }
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("http")) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      void confirmDiscardUnsavedWork("navigation").then((ok) => {
        if (ok) {
          navigate(href);
        }
      });
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [navigate]);

  if (!pending) {
    return null;
  }

  const stay = () => {
    pending.resolve(false);
    setPending(null);
  };
  const discard = () => {
    pending.resolve(true);
    setPending(null);
  };
  const discardLabel =
    pending.reason === "logout" ? t("note.discardAndLogout") : t("note.discardAndContinue");

  return (
    <div className="modal-backdrop" role="presentation">
      <div
        className="modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="unsaved-note-title"
        aria-describedby="unsaved-note-body"
      >
        <h2 id="unsaved-note-title">{t("note.unsavedTitle")}</h2>
        <p id="unsaved-note-body">{t("note.unsavedBody")}</p>
        <div className="modal-actions">
          <button type="button" className="button" onClick={stay} autoFocus>
            {t("note.stay")}
          </button>
          <button type="button" className="button danger" onClick={discard}>
            {discardLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
