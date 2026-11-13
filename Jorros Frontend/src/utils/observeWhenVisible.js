// Reveal once when a section approaches the viewport. The fallback keeps
// content available in older browsers and restricted browser environments.
export function observeWhenVisible(element, reveal, Observer = globalThis.IntersectionObserver) {
    let active = true, observer;
    const show = () => {
        if (!active) return;
        active = false;
        observer?.disconnect();
        reveal();
    };
    if (!element || typeof Observer !== "function") show();
    else {
        try {
            observer = new Observer(entries => {
                if (entries.some(entry => entry.isIntersecting)) show();
            }, { rootMargin: "200px 0px" });
            observer.observe(element);
        } catch { show(); }
    }
    return () => { active = false; observer?.disconnect(); };
}
