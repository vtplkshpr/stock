import { createContext, useContext } from "react";

export type Panel =
  | { kind: "content"; nodeId: string }
  | { kind: "news"; id: number; title: string }
  | { kind: "text"; title: string; text: string };

export interface DiagramActions {
  toggle: (id: string) => void;
  focus: (id: string) => void;
  openPanel: (panel: Panel) => void;
  selectedId: string | null;
  hoveredTicker: string | null;
  setHoveredTicker: (ticker: string | null) => void;
}

export const ActionsContext = createContext<DiagramActions | null>(null);

export function useActions(): DiagramActions {
  const actions = useContext(ActionsContext);
  if (!actions) throw new Error("ActionsContext is missing");
  return actions;
}
