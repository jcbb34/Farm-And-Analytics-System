"use client";

import { Component } from "react";

// An analytics rendering issue must not take down crop registration or the crop records list.
export default class CropAnalyticsErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { failed: false };
    }

    static getDerivedStateFromError() {
        return { failed: true };
    }

    componentDidCatch(error, info) {
        console.error("Crop Analytics failed to render:", error, info);
    }

    render() {
        if (this.state.failed) {
            return (
                <section className="crop-analytics-section" role="alert">
                    <div className="workforce-error">
                        Crop records are still available, but analytics could not be displayed.
                        <button type="button" className="workforce-button secondary"
                            onClick={() => this.setState({ failed: false })}>
                            Retry analytics
                        </button>
                    </div>
                </section>
            );
        }
        return this.props.children;
    }
}
