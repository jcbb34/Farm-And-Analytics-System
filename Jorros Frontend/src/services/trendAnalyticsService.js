import { httpClient } from "./httpClient.js";

export const trendAnalyticsService = Object.freeze({
    async getOverview(months = 12) {
        const response = await httpClient.get(
            "/analytics/overview",
            {
                query: { months },
            }
        );

        return response?.data ?? response;
    },

    async getTrends(months = 12) {
        const response = await httpClient.get(
            "/analytics/trends",
            {
                query: { months },
            }
        );

        return response?.data ?? response;
    },
});
