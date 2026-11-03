import { useEffect } from "react";

import { useUnsavedChanges } from "../context/UnsavedChangesContext.jsx";

export function useUnsavedForm(
    source,
    isDirty,
    { clearOnUnmount = true } = {}
) {
    const { markDirty, markClean } =
        useUnsavedChanges();

    useEffect(() => {
        if (isDirty) {
            markDirty(source);
        } else {
            markClean(source);
        }

        return () => {
            if (clearOnUnmount) {
                markClean(source);
            }
        };
    }, [
        source,
        isDirty,
        clearOnUnmount,
        markDirty,
        markClean,
    ]);
}
