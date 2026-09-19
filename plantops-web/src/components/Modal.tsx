import { useEffect, useRef, type ReactNode } from "react";
import { useI18n } from "../i18n";
export function Modal({title, children, onClose}: {title: string; children: ReactNode; onClose: () => void}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {const dialog = ref.current; dialog?.showModal(); return () => dialog?.close();}, []);
  return <dialog ref={ref} className="asset-dialog" aria-label={title} onCancel={onClose} onClick={e => {if (e.target === ref.current) onClose();}}>
    <div className="dialog-heading"><h2>{title}</h2><button aria-label={t("Close dialog")} onClick={onClose}>{t("Close")}</button></div>{children}
  </dialog>;
}
