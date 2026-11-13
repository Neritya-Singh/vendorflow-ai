import { useEffect, useRef } from "react";

/** True when the key press belongs to a text field or an open dialog, not to the page. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (target as HTMLInputElement).type;
    return !["checkbox", "radio", "button", "submit", "reset"].includes(type);
  }
  return false;
}

/**
 * Single-key page shortcuts (J, K, Enter, /, A, C, R, ?). Disabled while typing
 * in a field, while any modal dialog is open, and when a modifier key is held.
 */
export function useShortcuts(handlers: Record<string, (e: KeyboardEvent) => void>, enabled = true) {
  const ref = useRef(handlers);
  ref.current = handlers;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      if (isTypingTarget(e.target)) return;
      if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const handler = ref.current[key];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
