"use client";

import {
    BarChart,
    PieChart,
    colorizeData,
} from "./ReportCharts.jsx";
import { formatMonthLabel } from "../reportUtils.js";

const money = (value) =>
    `₱${Number(value || 0).toLocaleString("en-PH", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;

const number = (value, digits = 2) =>
    Number(value || 0).toLocaleString("en-PH", {
        maximumFractionDigits: digits,
    });

const hasValues = (items = []) =>
    items.some((item) => Number(item?.value || 0) > 0);

function ReportsAnalytics({ activeTab, reports }) {
    const latestSnapshot = (category, reportTypes = []) => {
        const preferred = reports.find(
            (item) =>
                item.category === category &&
                (reportTypes.length === 0 || reportTypes.includes(item.reportType)) &&
                item.snapshot &&
                Object.keys(item.snapshot).length > 0
        );

        if (preferred) {
            return preferred.snapshot;
        }

        const fallback = reports.find(
            (item) =>
                item.category === category &&
                item.snapshot &&
                Object.keys(item.snapshot).length > 0
        );

        return fallback?.snapshot || {};
    };

    const cropSnapshot = latestSnapshot("Crop");
    const livestockSnapshot = latestSnapshot("Livestock");
    const productionSnapshot = latestSnapshot("Livestock", [
        "Production & Sales Summary",
        "Livestock Production",
        "Processing Summary",
    ]);
    const inventorySnapshot = latestSnapshot("Inventory");
    const farmSnapshot = latestSnapshot("Farm", ["Trend & Seasonal Analysis"]);
    const farmPerformanceSnapshot = latestSnapshot("Farm", [
        "Farm Performance Report",
        "Farm Summary",
    ]);

    const cropHarvestData = (cropSnapshot.monthlyHarvest || []).map((item) => ({
        label: formatMonthLabel(item.label),
        value: Number(Number(item.value || 0).toFixed(2)),
    }));

    const cropPerformanceData = (cropSnapshot.cropPerformance || []).map((item) => ({
        crop: item.crop,
        area: Number(item.areaHa || 0),
        planted: Number(item.quantityPlanted || 0),
        surviving: Number(item.currentSurviving || 0),
        survivalRate: Number(item.survivalRatePercent || 0),
        harvest: Number(Number(item.harvestKg || 0).toFixed(2)),
        yield: Number(Number(item.yieldKgPerHa || 0).toFixed(2)),
    }));

    const livestockTypeData = colorizeData(
        (livestockSnapshot.typeDistribution || []).map((item) => ({
            label: item.label,
            value: Number(item.value || 0),
        }))
    );

    const livestockHealthData = colorizeData(
        (livestockSnapshot.healthDistribution || []).map((item) => ({
            label: item.label,
            value: Number(item.value || 0),
        }))
    );

    const livestockGrowthData = colorizeData(
        (livestockSnapshot.growthDistribution || []).map((item) => ({
            label: item.label,
            value: Number(item.value || 0),
        }))
    );

    const productionOutputData = (productionSnapshot.productionTotals || []).map(
        (item) => ({
            label: `${item.outputType} (${item.unit})`,
            value: Number(item.quantity || 0),
        })
    );

    const paymentStatusData = colorizeData(
        (productionSnapshot.paymentStatusDistribution || []).map((item) => ({
            label: item.label,
            value: Number(item.value || 0),
        }))
    );

    const inventoryMovementData = (inventorySnapshot.movementDistribution || []).map(
        (item) => ({
            label: item.label,
            value: Number(item.value || 0),
        })
    );

    const inventoryCategoryData = colorizeData(
        (inventorySnapshot.categoryDistribution || []).map((item) => ({
            label: item.label,
            value: Number(item.value || 0),
        }))
    );

    const trends = farmSnapshot.trendAnalysis || {};
    const monthlyTrendRows = trends.monthly || [];
    const seasonalRows = trends.seasonal || [];
    const factorRows = trends.factorAnalysis || [];
    const trendGrowthRows = trends.growthSummary || [];
    const coverage = trends.dataCoverage || {};

    const monthlyCropYieldData = monthlyTrendRows.map((item) => ({
        label: item.label || formatMonthLabel(item.month),
        value: Number(item.cropYieldKg || 0),
    }));

    const monthlyRainfallData = monthlyTrendRows
        .filter((item) => item.averageRainfallMm != null)
        .map((item) => ({
            label: item.label || formatMonthLabel(item.month),
            value: Number(item.averageRainfallMm || 0),
        }));

    const seasonalCropYieldData = seasonalRows.map((item) => ({
        label: item.season,
        value: Number(item.cropYieldKg || 0),
    }));

    const seasonalFeedData = seasonalRows.map((item) => ({
        label: item.season,
        value: Number(item.feedConsumptionKg || 0),
    }));

    const topCropData = (trends.topCrops || []).map((item) => ({
        label: item.crop,
        value: Number(item.yieldKg || 0),
    }));

    const hasCropHarvest = hasValues(cropHarvestData);
    const hasCropPerformance = cropPerformanceData.length > 0;
    const hasLivestockTypes = hasValues(livestockTypeData);
    const hasLivestockHealth = hasValues(livestockHealthData);
    const hasLivestockGrowth = hasValues(livestockGrowthData);
    const hasProductionOutput = hasValues(productionOutputData);
    const hasPaymentStatus = hasValues(paymentStatusData);
    const hasInventoryMovements = hasValues(inventoryMovementData);
    const hasInventoryCategories = hasValues(inventoryCategoryData);
    const hasTrendData = Object.keys(trends).length > 0;

    let content = null;

    if (activeTab === "Farm Performance") {
        if (Object.keys(farmPerformanceSnapshot).length === 0) return null;

        const farmKpis = farmPerformanceSnapshot.executiveKpis || [];
        const farmRisks = farmPerformanceSnapshot.riskFlags || [];
        const varianceRows = farmPerformanceSnapshot.performanceVariance || [];

        content = (
            <>
                <article className="reports-page-chart-card reports-page-finance-card reports-page-span-full">
                    <div className="reports-page-chart-heading">
                        <div>
                            <h3>Farm Performance Overview</h3>
                            <p>Management KPIs combined from crops, livestock, production and sales, and inventory.</p>
                        </div>
                        <span className="material-symbols-outlined">monitoring</span>
                    </div>
                    <div className="reports-page-business-kpis">
                        {farmKpis.map((item) => {
                            const unit = String(item.unit || "");
                            const display = unit === "PHP"
                                ? money(item.value)
                                : `${number(item.value, unit === "kg/day" ? 4 : 2)}${unit ? ` ${unit}` : ""}`;
                            return (
                                <Kpi
                                    key={item.label}
                                    label={item.label}
                                    value={display}
                                    icon="analytics"
                                />
                            );
                        })}
                    </div>
                </article>

                {varianceRows.length > 0 && (
                    <ChartCard
                        title="Performance & Variance"
                        description="Actual values compared only with recorded plans, biological capacity, schedule references, or other defensible baselines."
                        icon="difference"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr><th>Metric</th><th>Actual</th><th>Reference</th><th>Variance</th></tr>
                                </thead>
                                <tbody>
                                    {varianceRows.map((item) => (
                                        <tr key={item.metric}>
                                            <td>{item.metric}</td>
                                            <td>{number(item.actual, 3)} {item.unit === "PHP" ? "PHP" : item.unit}</td>
                                            <td>{number(item.reference, 3)} {item.unit === "PHP" ? "PHP" : item.unit}</td>
                                            <td>{Number(item.variance || 0) >= 0 ? "+" : ""}{number(item.variance, 3)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {farmRisks.length > 0 && (
                    <ChartCard
                        title="Risks & Issues"
                        description="Rule-based operational flags from the latest farm performance report."
                        icon="warning"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr><th>Level</th><th>Area</th><th>Issue</th><th>Action</th></tr>
                                </thead>
                                <tbody>
                                    {farmRisks.map((item, index) => (
                                        <tr key={`${item.area}-${item.issue}-${index}`}>
                                            <td>{item.level}</td>
                                            <td>{item.area}</td>
                                            <td>{item.issue}</td>
                                            <td>{item.action}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}
            </>
        );
    } else if (activeTab === "Crop Reports") {
        if (!hasCropHarvest && !hasCropPerformance) return null;

        content = (
            <>
                {hasCropHarvest && (
                    <ChartCard
                        title="Monthly Harvest"
                        description="Recorded crop harvest from the latest generated crop report."
                        icon="agriculture"
                    >
                        <BarChart data={cropHarvestData} unit=" kg" />
                    </ChartCard>
                )}

                {hasCropPerformance && (
                    <ChartCard
                        title="Yield vs Area"
                        description="Crop area, harvest, and calculated yield from the latest report snapshot."
                        icon="monitoring"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Crop</th>
                                        <th>Area</th>
                                        <th>Planted</th>
                                        <th>Surviving</th>
                                        <th>Survival</th>
                                        <th>Harvest</th>
                                        <th>Yield</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {cropPerformanceData.map((item) => (
                                        <tr key={`${item.crop}-${item.area}`}>
                                            <td>{item.crop}</td>
                                            <td>{item.area} ha</td>
                                            <td>{number(item.planted, 0)}</td>
                                            <td>{number(item.surviving, 0)}</td>
                                            <td>{number(item.survivalRate)}%</td>
                                            <td>{number(item.harvest)} kg</td>
                                            <td>{number(item.yield)} kg/ha</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}
            </>
        );
    } else if (activeTab === "Production & Sales") {
        const metrics = productionSnapshot.metrics || {};
        const productionRows = productionSnapshot.productionRecords || [];
        const processingRows = productionSnapshot.processingRecords || [];
        const salesRows = productionSnapshot.salesRecords || [];
        const paymentRows = productionSnapshot.paymentRecords || [];

        if (Object.keys(productionSnapshot).length === 0) return null;

        content = (
            <>
                <article className="reports-page-chart-card reports-page-finance-card reports-page-span-full">
                    <div className="reports-page-chart-heading">
                        <div>
                            <h3>Production &amp; Sales Performance</h3>
                            <p>
                                Actual production, processed output, sales value, cash collections,
                                receivables, and remaining sale inventory for the report period.
                            </p>
                        </div>
                        <span className="material-symbols-outlined">point_of_sale</span>
                    </div>

                    <div className="reports-page-business-kpis">
                        <Kpi label="Gross Sales" value={money(metrics.grossSalesValue ?? metrics.salesRevenue)} icon="receipt_long" />
                        <Kpi label="Cash Receipts" value={money(metrics.cashCollected)} icon="payments" />
                        <Kpi label="Collection Rate" value={`${number(metrics.collectionRatePercent)}%`} icon="price_check" />
                        <Kpi label="Receivables" value={money(metrics.outstandingBalance)} icon="account_balance_wallet" />
                        <Kpi label="Sales Records" value={number(metrics.salesRecordsInPeriod, 0)} icon="shopping_cart" />
                        <Kpi label="Egg Production" value={`${number(metrics.eggProductionPcs, 0)} pcs`} icon="egg_alt" />
                        <Kpi label="Eggs Sold" value={`${number(metrics.eggSoldPcs, 0)} pcs`} icon="sell" />
                        <Kpi label="Eggs Available" value={`${number(metrics.eggsAvailablePcs, 0)} pcs`} icon="inventory_2" />
                        <Kpi label="Egg Sell-through" value={`${number(metrics.eggSellThroughPercent)}%`} icon="trending_up" />
                        <Kpi label="Avg. Laying Rate" value={`${number(metrics.averageLayingRatePercent)}%`} icon="monitoring" />
                        <Kpi label="Animals Processed" value={`${number(metrics.animalsProcessedHead, 0)} head`} icon="manufacturing" />
                        <Kpi label="Meat Output" value={`${number(metrics.meatOutputKg, 3)} kg`} icon="inventory_2" />
                        <Kpi label="Meat Sold" value={`${number(metrics.meatSoldKg, 3)} kg`} icon="sell" />
                        <Kpi label="Meat Available" value={`${number(metrics.meatAvailableKg, 3)} kg`} icon="warehouse" />
                        <Kpi label="Meat Sell-through" value={`${number(metrics.meatSellThroughPercent)}%`} icon="trending_up" />
                        <Kpi label="Dressing Yield" value={`${number(metrics.averageDressingYieldPercent)}%`} icon="analytics" />
                    </div>
                </article>

                {hasProductionOutput && (
                    <ChartCard
                        title="Production Output"
                        description="Livestock output quantities are kept in their recorded units instead of mixing unlike units."
                        icon="egg_alt"
                    >
                        <BarChart data={productionOutputData} unit="" />
                    </ChartCard>
                )}

                {hasPaymentStatus && (
                    <ChartCard
                        title="Sales Payment Status"
                        description="Distribution of paid, partial, and unpaid sales transactions."
                        icon="account_balance_wallet"
                    >
                        <PieChart data={paymentStatusData} />
                    </ChartCard>
                )}

                {productionRows.length > 0 && (
                    <ChartCard
                        title="Production Records"
                        description="Production period, source females, laying performance, output quantity, and remaining sale inventory."
                        icon="fact_check"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Livestock</th>
                                        <th>Output</th>
                                        <th>Period</th>
                                        <th>Qty</th>
                                        <th>Source Females</th>
                                        <th>Laying Rate</th>
                                        <th>Available</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {productionRows.slice(-16).reverse().map((item, index) => (
                                        <tr key={`${item.livestock}-${item.recordDate}-${item.outputType}-${index}`}>
                                            <td>{item.livestock}</td>
                                            <td>{item.outputType}</td>
                                            <td>
                                                {item.periodStartDate || item.recordDate}
                                                {" – "}
                                                {item.periodEndDate || item.recordDate}
                                            </td>
                                            <td>{number(item.quantity, 3)} {item.unit}</td>
                                            <td>{item.sourceFemaleQuantity ?? "—"}</td>
                                            <td>
                                                {item.layingRatePercent == null
                                                    ? "—"
                                                    : `${number(item.layingRatePercent)}%`}
                                            </td>
                                            <td>{number(item.availableQuantity, 3)} {item.unit}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {processingRows.length > 0 && (
                    <ChartCard
                        title="Livestock Processing"
                        description="Processed head count, live weight, meat output, and calculated dressing yield."
                        icon="manufacturing"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Livestock</th>
                                        <th>Date</th>
                                        <th>Head</th>
                                        <th>Live Weight</th>
                                        <th>Meat</th>
                                        <th>Yield</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {processingRows.slice(-12).reverse().map((item, index) => (
                                        <tr key={`${item.livestock}-${item.processingDate}-${index}`}>
                                            <td>{item.livestock}</td>
                                            <td>{item.processingDate}</td>
                                            <td>{item.animalsProcessed}</td>
                                            <td>{number(item.liveWeightKg, 3)} kg</td>
                                            <td>{number(item.meatOutputKg, 3)} kg</td>
                                            <td>{number(item.dressingYieldPercent)}%</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {salesRows.length > 0 && (
                    <ChartCard
                        title="Sales & Collections"
                        description="Gross amount, amount collected, remaining balance, and payment status per transaction."
                        icon="point_of_sale"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Sale</th>
                                        <th>Product</th>
                                        <th>Qty</th>
                                        <th>Gross</th>
                                        <th>Paid</th>
                                        <th>Balance</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {salesRows.slice(-16).reverse().map((item) => (
                                        <tr key={item.saleCode}>
                                            <td>{item.saleCode}</td>
                                            <td>{item.productType}</td>
                                            <td>{number(item.quantity, 3)} {item.unit}</td>
                                            <td>{money(item.totalAmount)}</td>
                                            <td>{money(item.amountPaid)}</td>
                                            <td>{money(item.balanceDue)}</td>
                                            <td>{item.paymentStatus}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {paymentRows.length > 0 && (
                    <ChartCard
                        title="Payment Collection History"
                        description="Actual payments received during the report period, including later collections on earlier sales."
                        icon="account_balance_wallet"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Sale</th>
                                        <th>Payment Date</th>
                                        <th>Amount</th>
                                        <th>Method</th>
                                        <th>Notes</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {paymentRows.slice(-16).reverse().map((item, index) => (
                                        <tr key={`${item.saleCode}-${item.paymentDate}-${index}`}>
                                            <td>{item.saleCode}</td>
                                            <td>{item.paymentDate}</td>
                                            <td>{money(item.amount)}</td>
                                            <td>{item.paymentMethod || "—"}</td>
                                            <td>{item.notes || "—"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}
            </>
        );
    } else if (activeTab === "Trend & Seasonal Analysis") {
        if (!hasTrendData) return null;

        content = (
            <>
                <article className="reports-page-chart-card reports-page-span-full">
                    <div className="reports-page-chart-heading">
                        <div>
                            <h3>Trend Data Coverage</h3>
                            <p>
                                Shows how much historical evidence supports the selected trend period.
                                Weather correlations remain descriptive and never imply causation.
                            </p>
                        </div>
                        <span className="material-symbols-outlined">query_stats</span>
                    </div>

                    <div className="reports-page-business-kpis">
                        <Kpi label="Months in Period" value={number(coverage.monthsInPeriod, 0)} icon="calendar_month" />
                        <Kpi label="Crop Yield Records" value={number(coverage.cropYieldRecords, 0)} icon="agriculture" />
                        <Kpi label="Weather Records" value={number(coverage.weatherRecords, 0)} icon="partly_cloudy_day" />
                        <Kpi label="Growth Measurements" value={number(coverage.livestockGrowthRecords, 0)} icon="monitoring" />
                        <Kpi label="Feeding Records" value={number(coverage.feedingRecords, 0)} icon="nutrition" />
                        <Kpi label="Production Records" value={number(coverage.livestockProductionRecords, 0)} icon="egg_alt" />
                        <Kpi
                            label="Rainfall-Yield Pairs"
                            value={`${number(coverage.rainfallYieldPairMonths, 0)} / ${number(coverage.monthsInPeriod, 0)} mo`}
                            icon="water_drop"
                        />
                        <Kpi
                            label="Feed-Growth Pairs"
                            value={`${number(coverage.feedGrowthPairMonths, 0)} / ${number(coverage.monthsInPeriod, 0)} mo`}
                            icon="query_stats"
                        />
                        <Kpi label="Voided Records Excluded" value={number(coverage.voidedProductionRecordsExcluded, 0)} icon="filter_alt" />
                    </div>
                </article>

                {hasValues(monthlyCropYieldData) && (
                    <ChartCard
                        title="Crop Yield Trend by Month"
                        description="Recorded harvested crop quantity for each month in the selected period."
                        icon="show_chart"
                    >
                        <BarChart data={monthlyCropYieldData} unit=" kg" />
                    </ChartCard>
                )}

                {hasValues(monthlyRainfallData) && (
                    <ChartCard
                        title="Recorded Rainfall Trend"
                        description="Average recorded rainfall by month from Weather History."
                        icon="rainy"
                    >
                        <BarChart data={monthlyRainfallData} unit=" mm" />
                    </ChartCard>
                )}

                {hasValues(seasonalCropYieldData) && (
                    <ChartCard
                        title="Crop Yield by Season"
                        description="Recorded crop yield grouped into Cool Dry, Hot Dry, and Rainy seasons."
                        icon="calendar_month"
                    >
                        <BarChart data={seasonalCropYieldData} unit=" kg" />
                    </ChartCard>
                )}

                {hasValues(seasonalFeedData) && (
                    <ChartCard
                        title="Feed Consumption by Season"
                        description="Actual livestock feed consumption grouped by the system's seasonal classification."
                        icon="nutrition"
                    >
                        <BarChart data={seasonalFeedData} unit=" kg" />
                    </ChartCard>
                )}

                {hasValues(topCropData) && (
                    <ChartCard
                        title="Top Crops by Recorded Yield"
                        description="Highest crop output in the selected historical period."
                        icon="leaderboard"
                    >
                        <BarChart data={topCropData} unit=" kg" />
                    </ChartCard>
                )}

                {factorRows.length > 0 && (
                    <ChartCard
                        title="Factor Analysis"
                        description="Pearson correlations from available monthly records. These associations are descriptive only and do not prove cause and effect."
                        icon="function"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Factor</th>
                                        <th>r</th>
                                        <th>Direction</th>
                                        <th>Strength</th>
                                        <th>Interpretation</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {factorRows.map((item) => (
                                        <tr key={item.factor}>
                                            <td>{item.factor}</td>
                                            <td>{item.correlation == null ? "—" : number(item.correlation, 3)}</td>
                                            <td>{item.direction}</td>
                                            <td>{item.strength}</td>
                                            <td>{item.note}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {trendGrowthRows.length > 0 && (
                    <ChartCard
                        title="Livestock Growth Trend"
                        description="Weight change and calculated average daily gain from historical measurements."
                        icon="trending_up"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Livestock</th>
                                        <th>Type</th>
                                        <th>Measurements</th>
                                        <th>Start Weight</th>
                                        <th>Latest Weight</th>
                                        <th>Total Change</th>
                                        <th>Avg. Daily Gain</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {trendGrowthRows.slice(0, 16).map((item) => (
                                        <tr key={item.livestockId}>
                                            <td>{item.recordName}</td>
                                            <td>{item.animalType}</td>
                                            <td>{item.measurements}</td>
                                            <td>{number(item.startWeightKg)} kg</td>
                                            <td>{number(item.latestWeightKg)} kg</td>
                                            <td>{number(item.totalChangeKg)} kg</td>
                                            <td>
                                                {item.averageDailyGainKg == null
                                                    ? "—"
                                                    : `${number(item.averageDailyGainKg, 4)} kg/day`}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {monthlyTrendRows.some((row) => Object.keys(row.production || {}).length > 0) && (
                    <ChartCard
                        title="Monthly Livestock Production"
                        description="Production is shown by output and unit so eggs, meat, milk, and other outputs are never added together incorrectly."
                        icon="table_chart"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Month</th>
                                        <th>Season</th>
                                        <th>Production</th>
                                        <th>Feed</th>
                                        <th>Avg. Daily Gain</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {monthlyTrendRows.map((item) => (
                                        <tr key={item.month}>
                                            <td>{item.label || formatMonthLabel(item.month)}</td>
                                            <td>{item.season}</td>
                                            <td>
                                                {Object.entries(item.production || {}).length === 0
                                                    ? "—"
                                                    : Object.entries(item.production || {})
                                                          .map(([label, value]) => `${label}: ${number(value, 3)}`)
                                                          .join(" • ")}
                                            </td>
                                            <td>{number(item.feedConsumptionKg, 3)} kg</td>
                                            <td>
                                                {item.averageDailyGainKg == null
                                                    ? "—"
                                                    : `${number(item.averageDailyGainKg, 4)} kg/day`}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}
            </>
        );
    } else if (activeTab === "Livestock Reports") {
        const metrics = livestockSnapshot.metrics || {};
        const growthRows = livestockSnapshot.growthRecords || [];
        const vaccinationRows = livestockSnapshot.vaccinationRecords || [];
        const reproductionRows = livestockSnapshot.reproductionRecords || [];

        if (Object.keys(livestockSnapshot).length === 0) return null;

        content = (
            <>
                <article className="reports-page-chart-card reports-page-span-full">
                    <div className="reports-page-chart-heading">
                        <div>
                            <h3>Livestock Monitoring Summary</h3>
                            <p>
                                Population, growth measurements, health, feeding requirement,
                                vaccination, and reproduction monitoring from the current livestock records.
                            </p>
                        </div>
                        <span className="material-symbols-outlined">pets</span>
                    </div>

                    <div className="reports-page-business-kpis">
                        <Kpi label="Total Head" value={number(metrics.totalHead, 0)} icon="pets" />
                        <Kpi label="Avg. Record Weight" value={`${number(metrics.averageRecordWeightKg)} kg`} icon="monitor_weight" />
                        <Kpi label="Daily Feed Need" value={`${number(metrics.dailyFeedKg, 3)} kg`} icon="nutrition" />
                        <Kpi label="Growth Measurements" value={number(metrics.growthMeasurementsInPeriod, 0)} icon="monitoring" />
                        <Kpi label="Avg. Daily Gain" value={`${number(metrics.averageDailyGainKg, 4)} kg/day`} icon="trending_up" />
                        <Kpi label="Planned Feed" value={`${number(metrics.plannedFeedKg, 3)} kg`} icon="nutrition" />
                        <Kpi label="Actual Feed" value={`${number(metrics.actualFeedKg, 3)} kg`} icon="scale" />
                        <Kpi label="Feed Adherence" value={`${number(metrics.feedAdherencePercent)}%`} icon="fact_check" />
                        <Kpi label="Vaccinations" value={number(metrics.vaccinationsInPeriod, 0)} icon="vaccines" />
                        <Kpi label="Reproduction Records" value={number(metrics.reproductionRecordsInPeriod, 0)} icon="family_restroom" />
                        <Kpi label="Offspring Recorded" value={number(metrics.offspringRecordedInPeriod, 0)} icon="child_care" />
                    </div>
                </article>

                {hasLivestockTypes && (
                    <ChartCard
                        title="Livestock by Type"
                        description="Current active head count by animal type."
                        icon="pets"
                    >
                        <BarChart data={livestockTypeData} unit="" />
                    </ChartCard>
                )}

                {hasLivestockHealth && (
                    <ChartCard
                        title="Health Status"
                        description="Current livestock head count by health classification."
                        icon="health_and_safety"
                    >
                        <PieChart data={livestockHealthData} />
                    </ChartCard>
                )}

                {hasLivestockGrowth && (
                    <ChartCard
                        title="Growth Status"
                        description="Current livestock head count by growth stage/status."
                        icon="monitoring"
                    >
                        <PieChart data={livestockGrowthData} />
                    </ChartCard>
                )}

                {growthRows.length > 0 && (
                    <ChartCard
                        title="Growth Measurements"
                        description="Historical weights with weight change and calculated average daily gain."
                        icon="trending_up"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Livestock</th>
                                        <th>Date</th>
                                        <th>Previous</th>
                                        <th>Current</th>
                                        <th>Change</th>
                                        <th>Days</th>
                                        <th>Daily Gain</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {growthRows.slice(-16).reverse().map((item, index) => (
                                        <tr key={`${item.livestock}-${item.measurementDate}-${index}`}>
                                            <td>{item.livestock}</td>
                                            <td>{item.measurementDate}</td>
                                            <td>{item.previousWeightKg == null ? "—" : `${number(item.previousWeightKg)} kg`}</td>
                                            <td>{number(item.weightKg)} kg</td>
                                            <td>{item.weightChangeKg == null ? "—" : `${number(item.weightChangeKg)} kg`}</td>
                                            <td>{item.daysSincePrevious ?? "—"}</td>
                                            <td>{item.averageDailyGainKg == null ? "—" : `${number(item.averageDailyGainKg, 4)} kg/day`}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {vaccinationRows.length > 0 && (
                    <ChartCard
                        title="Vaccination Records"
                        description="Vaccinations administered during the report period and their next due dates."
                        icon="vaccines"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Livestock</th>
                                        <th>Vaccine</th>
                                        <th>Administered</th>
                                        <th>Next Due</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {vaccinationRows.slice(-14).reverse().map((item, index) => (
                                        <tr key={`${item.livestock}-${item.dateAdministered}-${index}`}>
                                            <td>{item.livestock}</td>
                                            <td>{item.vaccine}</td>
                                            <td>{item.dateAdministered}</td>
                                            <td>{item.nextDue || "—"}</td>
                                            <td>{item.status || "—"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}

                {reproductionRows.length > 0 && (
                    <ChartCard
                        title="Reproduction Records"
                        description="Breeding, birth/hatch, offspring, and reproductive-status events in the report period."
                        icon="family_restroom"
                    >
                        <div className="reports-page-performance-table-wrapper">
                            <table className="reports-page-performance-table">
                                <thead>
                                    <tr>
                                        <th>Livestock</th>
                                        <th>Type</th>
                                        <th>Date</th>
                                        <th>Status</th>
                                        <th>Offspring</th>
                                        <th>Alive</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {reproductionRows.slice(-14).reverse().map((item, index) => (
                                        <tr key={`${item.livestock}-${item.eventDate}-${index}`}>
                                            <td>{item.livestock}</td>
                                            <td>{item.recordType}</td>
                                            <td>{item.eventDate}</td>
                                            <td>{item.reproductiveStatus || "—"}</td>
                                            <td>{item.offspringCount}</td>
                                            <td>{item.aliveOffspring}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </ChartCard>
                )}
            </>
        );
    } else if (activeTab === "Inventory Reports") {
        const metrics = inventorySnapshot.metrics || {};
        if (Object.keys(inventorySnapshot).length === 0) return null;

        content = (
            <>
                <article className="reports-page-chart-card reports-page-span-full">
                    <div className="reports-page-chart-heading">
                        <div>
                            <h3>Inventory Performance Summary</h3>
                            <p>Stock exposure, valuation, reorder need, and potential margin from the latest inventory report.</p>
                        </div>
                        <span className="material-symbols-outlined">inventory_2</span>
                    </div>
                    <div className="reports-page-business-kpis">
                        <Kpi label="Inventory Items" value={number(metrics.inventoryItems, 0)} icon="inventory_2" />
                        <Kpi label="Low Stock" value={number(metrics.lowStockItems, 0)} icon="warning" />
                        <Kpi label="Expiring" value={number(metrics.expiringItems, 0)} icon="event_busy" />
                        <Kpi label="Reorder Shortfall" value={number(metrics.reorderShortfallQuantity, 3)} icon="add_shopping_cart" />
                        <Kpi label="Cost Value" value={money(metrics.costValue)} icon="payments" />
                        <Kpi label="Retail Value" value={money(metrics.retailValue)} icon="sell" />
                        <Kpi label="Potential Margin" value={money(metrics.potentialMarginValue)} icon="trending_up" />
                    </div>
                </article>
                {hasInventoryMovements && (
                    <ChartCard
                        title="Stock Movements"
                        description="Inventory adjustments by movement type from the latest inventory report."
                        icon="inventory"
                    >
                        <BarChart data={inventoryMovementData} unit="" />
                    </ChartCard>
                )}

                {hasInventoryCategories && (
                    <ChartCard
                        title="Stock by Category"
                        description="Current inventory item distribution by category."
                        icon="inventory_2"
                    >
                        <PieChart data={inventoryCategoryData} />
                    </ChartCard>
                )}
            </>
        );
    } else {
        if (!hasCropHarvest && !hasLivestockHealth && !hasInventoryCategories) return null;

        content = (
            <>
                {hasCropHarvest && (
                    <ChartCard
                        title="Monthly Crop Harvest"
                        description="Latest crop harvest totals available in generated reports."
                        icon="agriculture"
                    >
                        <BarChart data={cropHarvestData} unit=" kg" />
                    </ChartCard>
                )}

                {hasLivestockHealth && (
                    <ChartCard
                        title="Livestock Health"
                        description="Latest reported livestock health distribution."
                        icon="health_and_safety"
                    >
                        <PieChart data={livestockHealthData} />
                    </ChartCard>
                )}

                {hasInventoryCategories && (
                    <ChartCard
                        title="Inventory by Category"
                        description="Latest reported inventory distribution."
                        icon="inventory_2"
                    >
                        <PieChart data={inventoryCategoryData} />
                    </ChartCard>
                )}
            </>
        );
    }

    return <section className="reports-page-analytics-grid">{content}</section>;
}

function Kpi({ label, value, icon }) {
    return (
        <div className="reports-page-business-kpi">
            <span className="material-symbols-outlined">{icon}</span>
            <div>
                <small>{label}</small>
                <strong>{value}</strong>
            </div>
        </div>
    );
}

function ChartCard({ title, description, icon, children }) {
    return (
        <article className="reports-page-chart-card">
            <div className="reports-page-chart-heading">
                <div>
                    <h3>{title}</h3>
                    <p>{description}</p>
                </div>
                <span className="material-symbols-outlined">{icon}</span>
            </div>
            {children}
        </article>
    );
}

export default ReportsAnalytics;
