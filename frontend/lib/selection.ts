"use client";

import { useCallback, useState } from "react";

export function useSelection() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const toggle = useCallback(
    (id: string) =>
      setSelected((s) => {
        const n = new Set(s);
        if (n.has(id)) n.delete(id);
        else n.add(id);
        return n;
      }),
    [],
  );
  const clear = useCallback(() => setSelected(new Set()), []);
  const selectAll = useCallback((ids: string[]) => setSelected(new Set(ids)), []);
  return { selected, toggle, clear, selectAll, ids: [...selected] };
}
