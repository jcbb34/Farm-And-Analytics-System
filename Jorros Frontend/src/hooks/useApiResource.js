import {
    useCallback,
    useEffect,
    useRef,
    useState,
} from "react";

export function useApiResource(
    loader,
    {
        initialData = null,
        immediate = true,
        dependencies = [],
    } = {}
) {
    const mountedRef = useRef(true);
    const requestIdRef = useRef(0);

    const [state, setState] = useState({
        data: initialData,
        status: immediate ? "loading" : "idle",
        error: null,
    });

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    const execute = useCallback(
        async (...args) => {
            const requestId = ++requestIdRef.current;

            setState((current) => ({
                ...current,
                status: "loading",
                error: null,
            }));

            try {
                const data = await loader(...args);

                if (
                    mountedRef.current &&
                    requestId === requestIdRef.current
                ) {
                    setState({
                        data,
                        status: "success",
                        error: null,
                    });
                }

                return data;
            } catch (error) {
                if (
                    mountedRef.current &&
                    requestId === requestIdRef.current
                ) {
                    setState((current) => ({
                        ...current,
                        status: "error",
                        error,
                    }));
                }

                throw error;
            }
        },
        // The caller controls the dependency array because loaders are
        // often inline functions that would otherwise reload endlessly.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [loader, ...dependencies]
    );

    useEffect(() => {
        if (!immediate) {
            return;
        }

        execute().catch(() => {
            // Error state is already stored by execute().
        });
    }, [execute, immediate]);

    return {
        ...state,
        isIdle: state.status === "idle",
        isLoading: state.status === "loading",
        isSuccess: state.status === "success",
        isError: state.status === "error",
        reload: execute,
        setData: (updater) =>
            setState((current) => ({
                ...current,
                data:
                    typeof updater === "function"
                        ? updater(current.data)
                        : updater,
            })),
    };
}
