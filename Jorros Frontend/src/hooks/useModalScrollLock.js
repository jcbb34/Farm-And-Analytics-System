import { useEffect } from "react";

let activeLocks = 0;
let originalStyles = null;

export default function useModalScrollLock(open) {
    useEffect(() => {
        if (!open) return undefined;

        if (activeLocks === 0) {
            const page = document.documentElement;
            const body = document.body;
            const scrollbarWidth = Math.max(0, window.innerWidth - page.clientWidth);

            originalStyles = {
                pageOverflow: page.style.overflow,
                bodyOverflow: body.style.overflow,
                bodyPaddingRight: body.style.paddingRight,
            };

            page.style.overflow = "hidden";
            body.style.overflow = "hidden";
            if (scrollbarWidth > 0) {
                const padding = Number.parseFloat(window.getComputedStyle(body).paddingRight) || 0;
                body.style.paddingRight = `${padding + scrollbarWidth}px`;
            }
        }

        activeLocks += 1;
        return () => {
            activeLocks -= 1;
            if (activeLocks === 0 && originalStyles) {
                document.documentElement.style.overflow = originalStyles.pageOverflow;
                document.body.style.overflow = originalStyles.bodyOverflow;
                document.body.style.paddingRight = originalStyles.bodyPaddingRight;
                originalStyles = null;
            }
        };
    }, [open]);
}
