"use client";

import { useVoidAuthorization } from "../../context/VoidAuthorizationContext.jsx";

import { farmDateKey } from "../../utils/farmCalendar.js";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import { confirmAction, notifyError, notifySuccess, promptAction } from "../../context/NotificationContext.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { livestockService } from "../../services/livestockService.js";
import { inventoryService } from "../../services/inventoryService.js";
import { productionSalesService } from "../../services/productionSalesService.js";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";
import { clearStableIdempotencyKey, stableIdempotencyKey } from "../../services/idempotencyKey.js";

import "./ProductionSales.css";
import "./ProductionSalesSearchFix.css";

const todayIso = () => farmDateKey();
const PAGE_SIZE = 50;
const money = (value) => `₱${Number(value || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const number = (value) => Number(value || 0).toLocaleString("en-PH", { maximumFractionDigits: 3 });
const sourceType = (item) => String(item?.source_type || (item?.crop_id ? "Crop" : "Livestock")).toLowerCase();
const sourceMatches = (item, scope) => {
    if (scope === "all") return true;
    const expected = scope === "crops" ? "crop" : scope;
    const sources = Array.isArray(item?.source_types) ? item.source_types.map((value) => String(value).toLowerCase()) : [];
    return sources.includes(expected) || sourceType(item) === expected;
};
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

function Modal({ open, title, subtitle, onClose, children, className = "" }) {
    useEffect(() => {
        if (!open) return undefined;
        const previousBodyOverflow = document.body.style.overflow;
        const previousPageOverflow = document.documentElement.style.overflow;
        document.body.style.overflow = "hidden";
        document.documentElement.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = previousBodyOverflow;
            document.documentElement.style.overflow = previousPageOverflow;
        };
    }, [open]);

    if (!open) return null;
    return (
        <div className="ps-modal-overlay" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
            <section className={`ps-modal ${className}`.trim()} role="dialog" aria-modal="true">
                <header className="ps-modal-header">
                    <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
                    <button type="button" className="ps-icon-button" onClick={onClose} aria-label="Close"><span className="material-symbols-outlined">close</span></button>
                </header>
                {children}
            </section>
        </div>
    );
}

function Field({ label, children, className = "" }) {
    return <label className={`ps-field ${className}`.trim()}><span>{label}</span>{children}</label>;
}

function FormFooter({ onClose, label, saving = false }) {
    return <footer className="ps-modal-footer"><button type="button" className="ps-secondary" onClick={onClose} disabled={saving}>Cancel</button><button type="submit" className="ps-primary" disabled={saving}>{saving ? "Saving..." : label}</button></footer>;
}

function EmptyState({ text }) { return <div className="ps-empty">{text}</div>; }
function TableState({ loading, rows, emptyText }) {
    if (loading) return <div className="ps-table-state">Loading records...</div>;
    if (!rows.length) return <EmptyState text={emptyText} />;
    return null;
}

function Summary({ icon, label, value }) {
    return <article><span className="material-symbols-outlined">{icon}</span><div><small>{label}</small><strong>{value}</strong></div></article>;
}

const tabsForScope = (scope) => {
    if (scope === "livestock") return [["overview", "Overview"], ["reproduction", "Breeding & Reproduction"], ["production", "Production"], ["processing", "Processing"], ["sales", "Sales Transactions"]];
    if (scope === "crops") return [["overview", "Overview"], ["harvests", "Harvests"], ["sales", "Sales Transactions"]];
    return [["overview", "Overview"], ["production", "Production"], ["sales", "Sales Transactions"]];
};

function ProductionSales() {
    const requestVoid = useVoidAuthorization();
    const { hasPermission } = useAuth();
    const canEdit = hasPermission("production_sales:update");

    const [scope, setScope] = useState("all");
    const [activeTab, setActiveTab] = useState("overview");
    const [overview, setOverview] = useState(null);
    const [livestock, setLivestock] = useState([]);
    const [inventoryProducts, setInventoryProducts] = useState([]);
    const [saleableProduction, setSaleableProduction] = useState([]);
    const [reproduction, setReproduction] = useState([]);
    const [production, setProduction] = useState([]);
    const [processing, setProcessing] = useState([]);
    const [sales, setSales] = useState([]);
    const [loaded, setLoaded] = useState(new Set());
    const [hasMore, setHasMore] = useState({});
    const [loading, setLoading] = useState(true);
    const [tabLoading, setTabLoading] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const [sourceLoading, setSourceLoading] = useState(false);
    const [sourceError, setSourceError] = useState("");
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [modal, setModal] = useState(null);
    const [selectedSale, setSelectedSale] = useState(null);
    const [salePayments, setSalePayments] = useState([]);
    const [mutationBusy, setMutationBusy] = useState(false);
    const productionRequestRef = useRef(null);
    const productionInFlightRef = useRef(false);
    const processingRequestRef = useRef(null);
    const saleRequestRef = useRef(null);
    const paymentRequestRef = useRef(null);

    const loadOverview = useCallback(async () => {
        setLoading(true); setError("");
        try {
            setOverview(await productionSalesService.getOverview());
        } catch (err) { setError(err?.message || "Unable to load Production & Sales."); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { loadOverview(); }, [loadOverview]);

    const loadTab = useCallback(async (tab, force = false) => {
        const dataTab = tab === "harvests" ? "production" : tab;
        if (dataTab === "overview" || (!force && loaded.has(dataTab))) return;
        setTabLoading(true);
        try {
            const options = { limit: PAGE_SIZE, offset: 0 };
            const rows = dataTab === "reproduction" ? await productionSalesService.getReproduction(options)
                : dataTab === "production" ? await productionSalesService.getProduction(options)
                : dataTab === "processing" ? await productionSalesService.getProcessing({ ...options, include_voided: false })
                : await productionSalesService.getSales(options);
            ({ reproduction: setReproduction, production: setProduction, processing: setProcessing,
                sales: setSales })[dataTab](rows);
            setHasMore((current) => ({ ...current, [dataTab]: rows.length === PAGE_SIZE }));
            setLoaded((current) => new Set([...current, dataTab]));
        } catch (err) { notifyError(err?.message || "Unable to load records.", "Load Failed"); }
        finally { setTabLoading(false); }
    }, [loaded]);

    const loadMore = async () => {
        const tab = activeTab === "harvests" ? "production" : activeTab;
        const records = { reproduction, production, processing, sales }[tab];
        if (tabLoading || loadingMore || !hasMore[tab] || !records) return;
        setLoadingMore(true);
        try {
            const options = { limit: PAGE_SIZE, offset: records.length };
            const rows = tab === "reproduction" ? await productionSalesService.getReproduction(options)
                : tab === "production" ? await productionSalesService.getProduction(options)
                : tab === "processing" ? await productionSalesService.getProcessing(options)
                : await productionSalesService.getSales(options);
            ({ reproduction: setReproduction, production: setProduction, processing: setProcessing,
                sales: setSales })[tab]((current) => [...current, ...rows.filter((row) =>
                    !current.some((existing) => existing.id === row.id))]);
            setHasMore((current) => ({ ...current, [tab]: rows.length === PAGE_SIZE }));
        } catch (err) { notifyError(err?.message || "Unable to load more records.", "Load Failed"); }
        finally { setLoadingMore(false); }
    };

    const loadLivestockSources = async (nextModal) => {
        try {
            setSourceLoading(true);
            setLivestock(await livestockService.getLivestock(false));
            setModal(nextModal);
        } catch (err) { notifyError(err?.message || "Unable to load livestock sources.", "Load Failed"); }
        finally { setSourceLoading(false); }
    };

    const loadSaleSources = async () => {
        if (sourceLoading) return;
        try {
            setSourceLoading(true);
            setSourceError("");
            const [animals, inventory, available] = await Promise.all([
                livestockService.getLivestock(false),
                inventoryService.getInventory(false, false),
                (async () => {
                    const lots = [];
                    let offset = 0;
                    // The server filters before paging, so spent history does
                    // not delay the sale form or hide older available stock.
                    while (true) {
                        const rows = await productionSalesService.getProduction({ available_only: true, limit: 500, offset });
                        lots.push(...rows);
                        if (rows.length < 500) break;
                        offset += rows.length;
                    }
                    return lots;
                })(),
            ]);
            setLivestock(animals);
            setInventoryProducts(inventory.filter((item) => item.isSaleable && Number(item.quantity || 0) > 0));
            setSaleableProduction(available);
        } catch (err) {
            setSourceError(err?.message || "Unable to load sale sources.");
            notifyError(err?.message || "Unable to load sale sources.", "Load Failed");
        }
        finally { setSourceLoading(false); }
    };
    const openSale = () => {
        setModal("sale");
        void loadSaleSources();
    };

    useFarmModuleUpdates(["production_sales", "crops", "livestock"], async () => {
        await loadOverview();
        if (activeTab !== "overview") await loadTab(activeTab, true);
    }, { editing: Boolean(modal) });

    const changeTab = async (tab) => { setSearch(""); setActiveTab(tab); await loadTab(tab); };
    const changeScope = (next) => { setScope(next); setActiveTab("overview"); setSearch(""); };
    const refreshAfterMutation = async (...tabs) => { await Promise.all([loadOverview(), ...tabs.map((tab) => loadTab(tab, true))]); };

    const query = search.trim().toLowerCase();
    const filteredReproduction = useMemo(() => reproduction.filter((item) => `${item.livestock_name} ${item.animal_code} ${item.record_type} ${item.reproductive_status || ""}`.toLowerCase().includes(query)), [reproduction, query]);
    const filteredProduction = useMemo(() => production.filter((item) => sourceMatches(item, scope) && `${item.source_name} ${item.source_code} ${item.output_type} ${item.destination || ""}`.toLowerCase().includes(query)), [production, query, scope]);
    const filteredProcessing = useMemo(() => processing.filter((item) => `${item.livestock_name} ${item.animal_code} ${item.quality_grade || ""}`.toLowerCase().includes(query)), [processing, query]);
    const filteredSales = useMemo(() => sales.filter((item) => sourceMatches(item, scope) && `${item.sale_code} ${item.source_name} ${item.product_type} ${item.buyer_name || ""} ${item.payment_status || ""}`.toLowerCase().includes(query)), [sales, query, scope]);

    const submitProduction = async (event) => {
        event.preventDefault();
        if (productionInFlightRef.current) return;
        const form = new FormData(event.currentTarget);
        const gross = Number(form.get("gross_quantity") || 0);
        const loss = Number(form.get("loss_quantity") || 0);
        const farmUse = Number(form.get("farm_use_quantity") || 0);
        const reserved = Number(form.get("reserved_quantity") || 0);
        const saleable = gross - loss - farmUse - reserved;
        if (saleable <= 0) { notifyError("Saleable output must be greater than zero after allocations.", "Invalid Production"); return; }
        const payload = {
            livestock_id: Number(form.get("livestock_id")), output_type: form.get("output_type"), record_date: form.get("record_date"),
            period_start_date: form.get("period_start_date") || null, period_end_date: form.get("period_end_date") || null,
            source_active_quantity: Number(form.get("source_active_quantity") || 0) || null,
            gross_quantity: gross, loss_quantity: loss, farm_use_quantity: farmUse, reserved_quantity: reserved,
            quantity: saleable, unit: form.get("unit"), quality_grade: form.get("quality_grade") || null,
            destination: "Available for sale", track_sale_inventory: true, notes: form.get("notes") || null,
        };
        const idempotencyKey = stableIdempotencyKey(productionRequestRef, payload, "production-output");
        productionInFlightRef.current = true;
        setMutationBusy(true);
        try {
            await productionSalesService.createProduction(payload, { idempotencyKey });
            await refreshAfterMutation("production");
            clearStableIdempotencyKey(productionRequestRef);
            notifySuccess("Production stock was recorded and is now available to Sales Transactions.", "Production Saved");
            setModal(null);
        } catch (err) { notifyError(err?.message || "Unable to save production output.", "Save Failed"); }
        finally { productionInFlightRef.current = false; setMutationBusy(false); }
    };

    const submitProcessing = async (event) => {
        event.preventDefault(); const form = new FormData(event.currentTarget);
        const payload = { livestock_id: Number(form.get("livestock_id")), processing_date: form.get("processing_date"), animals_processed: Number(form.get("animals_processed")), male_quantity: Number(form.get("male_quantity") || 0), female_quantity: Number(form.get("female_quantity") || 0), unknown_quantity: Number(form.get("unknown_quantity") || 0), live_weight_kg: form.get("live_weight_kg") ? Number(form.get("live_weight_kg")) : null, meat_output_kg: Number(form.get("meat_output_kg")), quality_grade: form.get("quality_grade") || null, destination: "Available for sale", notes: form.get("notes") || null };
        const idempotencyKey = stableIdempotencyKey(processingRequestRef, payload, "livestock-processing");
        setMutationBusy(true);
        try {
            await productionSalesService.createProcessing(payload, { idempotencyKey });
            clearStableIdempotencyKey(processingRequestRef);
            notifySuccess("Livestock quantity was reduced and meat stock was created for sale.", "Processing Recorded"); setModal(null); await refreshAfterMutation("processing", "production");
        } catch (err) { notifyError(err?.message || "Unable to record livestock processing.", "Processing Failed"); }
        finally { setMutationBusy(false); }
    };

    const submitSale = async (payload) => {
        const idempotencyKey = stableIdempotencyKey(saleRequestRef, payload, "farm-sale");
        setMutationBusy(true);
        try {
            await productionSalesService.createSale(payload, { idempotencyKey });
            clearStableIdempotencyKey(saleRequestRef);
            notifySuccess("Sale, stock, payment, and receivable totals were updated together.", "Sale Recorded"); setModal(null); await refreshAfterMutation("sales", "production");
        } catch (err) { notifyError(err?.message || "Unable to record sale.", "Sale Failed"); }
        finally { setMutationBusy(false); }
    };

    const submitPayment = async (event) => {
        event.preventDefault(); if (!selectedSale) return; const form = new FormData(event.currentTarget);
        const payload = { payment_date: form.get("payment_date"), amount: Number(form.get("amount")), payment_method: form.get("payment_method") || null, notes: form.get("notes") || null };
        const idempotencyKey = stableIdempotencyKey(paymentRequestRef, payload, `sale-payment-${selectedSale.id}`);
        setMutationBusy(true);
        try { await productionSalesService.addSalePayment(selectedSale.id, payload, { idempotencyKey }); clearStableIdempotencyKey(paymentRequestRef); notifySuccess("Payment recorded and receivable balance updated.", "Payment Saved"); setModal(null); setSelectedSale(null); await refreshAfterMutation("sales"); }
        catch (err) { notifyError(err?.message || "Unable to record payment.", "Payment Failed"); }
        finally { setMutationBusy(false); }
    };

    const openPayment = (sale) => { setSelectedSale(sale); setModal("payment"); };
    const openSaleDetails = async (sale) => {
        setSelectedSale(sale);
        setSalePayments([]);
        setModal("sale-details");
        try { setSalePayments(await productionSalesService.getSalePayments(sale.id)); }
        catch (err) { notifyError(err?.message || "Unable to load payment history.", "History Failed"); }
    };
    const handleVoidProcessing = async (item) => {
        try { if (!await requestVoid({ action: "processing", recordId: item.id, onStale: () => refreshAfterMutation("processing", "production") })) return; notifySuccess("Processing was reversed.", "Processing Voided"); await refreshAfterMutation("processing", "production"); } catch (err) { notifyError(err?.message || "Unable to void processing.", "Void Failed"); }
    };
    const handleVoidSale = async (item) => {
        try { if (!await requestVoid({ action: "sale", recordId: item.id, onStale: () => refreshAfterMutation("sales", "production") })) return; notifySuccess("Sale was voided and source quantities were restored.", "Sale Voided"); await refreshAfterMutation("sales", "production"); } catch (err) { notifyError(err?.message || "Unable to void sale.", "Void Failed"); }
    };

    const printReceipt = async (sale) => {
        try {
            const receipt = await productionSalesService.getSaleReceipt(sale.id);
            const s = receipt.sale;
            const popup = window.open("", "_blank", "width=760,height=820");
            if (!popup) { notifyError("Allow pop-ups to print the receipt.", "Receipt Blocked"); return; }
            const itemRows = (s.items || []).map((item) => `<tr><td>${escapeHtml(item.product_type)}<small>${escapeHtml(item.source_type)} • ${escapeHtml(item.source_name)}</small></td><td>${escapeHtml(number(item.quantity))} ${escapeHtml(item.unit)}</td><td>${escapeHtml(money(item.unit_price))}</td><td>${escapeHtml(money(item.line_total))}</td></tr>`).join("");
            const paymentRows = (receipt.payments || []).map((item) => `<tr><td>${escapeHtml(item.payment_date)}</td><td>${escapeHtml(item.payment_method || "Not specified")}</td><td>${escapeHtml(item.recorded_by_name || "System user")}</td><td>${escapeHtml(money(item.amount))}</td></tr>`).join("");
            popup.document.write(`<!doctype html><html><head><title>${escapeHtml(receipt.receipt_number)}</title><style>body{font-family:Arial,sans-serif;padding:32px;color:#222}.head{text-align:center;border-bottom:2px solid #176b35;padding-bottom:16px}table{width:100%;border-collapse:collapse;margin:18px 0}th,td{text-align:left;padding:9px;border-bottom:1px solid #ddd}th{background:#f1f7f3}td small{display:block;color:#66756b;margin-top:3px}.row{display:flex;justify-content:space-between;gap:24px;padding:8px 0;border-bottom:1px solid #eee}.total{font-size:20px;font-weight:700}.balance{color:#b42318}.foot{margin-top:28px;font-size:12px;color:#666}@media print{button{display:none}}</style></head><body><div class="head"><h2>${escapeHtml(receipt.farm_name)}</h2><div>SALES RECEIPT</div><strong>${escapeHtml(receipt.receipt_number)}</strong></div><p><b>Transaction:</b> ${escapeHtml(s.sale_code)}<br><b>Date:</b> ${escapeHtml(s.sale_date)}<br><b>Customer:</b> ${escapeHtml(s.buyer_name || "Walk-in / Not specified")}</p><table><thead><tr><th>Product</th><th>Quantity</th><th>Unit Price</th><th>Amount</th></tr></thead><tbody>${itemRows}</tbody></table><div class="row total"><span>Total</span><b>${escapeHtml(money(s.total_amount))}</b></div><div class="row"><span>Amount Paid</span><b>${escapeHtml(money(s.amount_paid))}</b></div><div class="row balance"><span>Balance</span><b>${escapeHtml(money(s.balance_due))}</b></div><div class="row"><span>Payment Status</span><b>${escapeHtml(s.payment_status)}</b></div>${paymentRows ? `<h3>Payment History</h3><table><thead><tr><th>Date</th><th>Method</th><th>Recorded By</th><th>Amount</th></tr></thead><tbody>${paymentRows}</tbody></table>` : ""}<p class="foot">Recorded by: ${escapeHtml(s.recorded_by_name || "System user")}<br>This receipt reflects the saved transaction. Voided transactions remain part of the audit history.</p><button onclick="window.print()">Print / Save as PDF</button></body></html>`);
            popup.document.close(); popup.focus();
        } catch (err) { notifyError(err?.message || "Unable to generate receipt.", "Receipt Failed"); }
    };

    const scopeTabs = tabsForScope(scope);
    const actionButton = (() => {
        if (!canEdit || activeTab === "overview") return null;
        if (scope === "livestock" && activeTab === "reproduction") return <button className="ps-primary" type="button" onClick={() => { window.location.href = "/livestock"; }}><span className="material-symbols-outlined">family_restroom</span>Manage in Livestock</button>;
        if (scope === "livestock" && activeTab === "production") return <button className="ps-primary" type="button" disabled={sourceLoading} onClick={() => loadLivestockSources("production")}><span className="material-symbols-outlined">egg_alt</span>{sourceLoading ? "Loading sources..." : "Record Production"}</button>;
        if (scope === "livestock" && activeTab === "processing") return <button className="ps-primary" type="button" disabled={sourceLoading} onClick={() => loadLivestockSources("processing")}><span className="material-symbols-outlined">manufacturing</span>{sourceLoading ? "Loading sources..." : "Record Processing"}</button>;
        if (scope === "crops" && activeTab === "harvests") return <button className="ps-primary" type="button" onClick={() => { window.location.href = "/crops?addYield=1"; }}><span className="material-symbols-outlined">agriculture</span>Record Harvest</button>;
        return null;
    })();

    const summaryCards = (() => {
        if (scope === "livestock") {
            const cards = [
                ["pets", "Active Livestock", number(overview?.active_livestock)],
                ["egg_alt", "Eggs Available", `${number(overview?.eggs_available)} pcs`],
                ["inventory_2", "Meat Available", `${number(overview?.meat_available_kg)} kg`],
            ];
            if (Number(overview?.milk_available_l || 0) > 0) cards.push(["water_drop", "Milk Available", `${number(overview?.milk_available_l)} L`]);
            cards.push(["receipt_long", "Livestock Sales", money(overview?.livestock_revenue)], ["payments", "Cash Collected", money(overview?.livestock_cash_collected)], ["account_balance_wallet", "Receivables", money(overview?.livestock_outstanding_balance)]);
            return cards;
        }
        if (scope === "crops") return [
            ["agriculture", "Harvest Ready", number(overview?.harvest_ready_crops)],
            ["inventory_2", "Crop Quantity Available", `${number(overview?.crop_available_kg)} kg`],
            ["warehouse", "Crop Products Available", number(overview?.crop_product_lots)],
            ["receipt_long", "Crop Sales", money(overview?.crop_revenue)],
            ["payments", "Cash Collected", money(overview?.crop_cash_collected)],
            ["account_balance_wallet", "Receivables", money(overview?.crop_outstanding_balance)],
        ];
        return [
            ["pets", "Active Livestock", number(overview?.active_livestock)],
            ["agriculture", "Harvest Ready Crops", number(overview?.harvest_ready_crops)],
            ["warehouse", "Products Available for Sale", number((overview?.crop_product_lots || 0) + (overview?.livestock_product_lots || 0))],
            ["receipt_long", "Gross Sales", money(overview?.total_revenue)],
            ["payments", "Cash Collected", money(overview?.cash_collected)],
            ["account_balance_wallet", "Receivables", money(overview?.outstanding_balance)],
        ];
    })();

    return (
        <div className="ps-layout"><Sidebar />
            <main className="ps-content">
                <header className="ps-header"><div><h1>Production &amp; Sales</h1><p>Track farm outputs, livestock processing, crop harvest stock, sales, collections, and balances in one connected workflow.</p></div><AppHeaderActions /></header>
                <div className="ps-scope-toolbar">
                    <div className="ps-scope-switch" role="group" aria-label="Production source filter">
                        {[["all", "All"], ["livestock", "Livestock"], ["crops", "Crops"]].map(([key, label]) => (
                            <button key={key} className={scope === key ? "active" : ""} onClick={() => changeScope(key)} type="button">{label}</button>
                        ))}
                    </div>
                    {canEdit && (
                        <button className="ps-primary ps-record-sale-button" type="button" disabled={sourceLoading} onClick={openSale}>
                            <span className="material-symbols-outlined">point_of_sale</span>
                            {sourceLoading ? "Loading sources..." : "Record Sale"}
                        </button>
                    )}
                </div>
                {error && <div className="ps-error"><span>{error}</span><button type="button" onClick={loadOverview}>Retry</button></div>}
                <section className="ps-summary-grid ps-summary-grid-six">{summaryCards.map(([icon,label,value]) => <Summary key={label} icon={icon} label={label} value={loading ? "—" : value} />)}</section>
                <section className="ps-panel">
                    <div className="ps-toolbar"><nav className="ps-tabs">{scopeTabs.map(([key,label]) => <button type="button" key={key} className={activeTab === key ? "active" : ""} onClick={() => changeTab(key)}>{label}</button>)}</nav>
                        {activeTab !== "overview" && <div className="ps-actions"><div className="ps-search"><span className="material-symbols-outlined">search</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search loaded records..." /></div>{actionButton}</div>}
                    </div>
                    {activeTab === "overview" && <Overview summary={overview} loading={loading} scope={scope} />}
                    {activeTab === "reproduction" && <ReproductionTable rows={filteredReproduction} loading={tabLoading} />}
                    {(activeTab === "production" || activeTab === "harvests") && <ProductionTable rows={filteredProduction} loading={tabLoading} cropMode={activeTab === "harvests"} />}
                    {activeTab === "processing" && <ProcessingTable rows={filteredProcessing} loading={tabLoading} canEdit={canEdit} onVoid={handleVoidProcessing} />}
                    {activeTab === "sales" && <SalesTable rows={filteredSales} loading={tabLoading} canEdit={canEdit} onDetails={openSaleDetails} onPayment={openPayment} onReceipt={printReceipt} onVoid={handleVoidSale} />}
                    {activeTab !== "overview" && hasMore[activeTab === "harvests" ? "production" : activeTab] && <div className="ps-pagination"><button className="ps-secondary" type="button" disabled={tabLoading || loadingMore} onClick={loadMore}>{loadingMore ? "Loading..." : "Load 50 more records"}</button></div>}
                </section>
            </main>
            <ProductionModal saving={mutationBusy} open={modal === "production"} livestock={livestock} onClose={() => { if (!productionInFlightRef.current) setModal(null); }} onSubmit={submitProduction} />
            <ProcessingModal open={modal === "processing"} livestock={livestock} saving={mutationBusy} onClose={() => setModal(null)} onSubmit={submitProcessing} />
            <SaleModal open={modal === "sale"} scope={scope} livestock={livestock} inventory={inventoryProducts} production={saleableProduction} sourceLoading={sourceLoading} sourceError={sourceError} onRetry={loadSaleSources} saving={mutationBusy} onClose={() => setModal(null)} onSubmit={submitSale} />
            <PaymentModal open={modal === "payment"} sale={selectedSale} saving={mutationBusy} onClose={() => { setModal(null); setSelectedSale(null); }} onSubmit={submitPayment} />
            <SaleDetailsModal open={modal === "sale-details"} sale={selectedSale} payments={salePayments} canEdit={canEdit} onClose={() => { setModal(null); setSelectedSale(null); setSalePayments([]); }} onPayment={() => setModal("payment")} onReceipt={() => printReceipt(selectedSale)} />
        </div>
    );
}

function Overview({ summary, loading, scope }) {
    if (loading) return <div className="ps-table-state">Loading overview...</div>;
    const recentProduction = (summary?.recent_production || []).filter((item) => sourceMatches(item, scope));
    const recentSales = (summary?.recent_sales || []).filter((item) => sourceMatches(item, scope));
    return <div className="ps-overview-grid">
        <article className="ps-overview-card"><h3>Recent Production</h3><p>Crop harvests and livestock outputs use the same sale-stock ledger.</p>{recentProduction.length === 0 ? <EmptyState text="No recent production records." /> : recentProduction.map((item) => <div className="ps-recent-row" key={item.id}><div><strong>{item.source_name}</strong><span>{item.source_type} • {item.output_type} • {item.record_date}{item.laying_rate_percent != null ? ` • ${number(item.laying_rate_percent)}% laying rate` : ""}</span></div><b>{number(item.gross_quantity ?? item.quantity)} {item.unit}</b></div>)}</article>
        <article className="ps-overview-card"><h3>Recent Sales</h3><p>Gross value, collected cash, and receivables are tracked from the same transaction.</p>{recentSales.length === 0 ? <EmptyState text="No recent sales transactions." /> : recentSales.map((item) => <div className="ps-recent-row" key={item.id}><div><strong>{item.sale_code} • {item.product_type}</strong><span>{item.source_type} • {item.sale_date} • {item.payment_status}</span></div><b>{money(item.total_amount)}</b></div>)}</article>
    </div>;
}

function ReproductionTable({ rows, loading }) {
    const state = <TableState loading={loading} rows={rows} emptyText="No reproduction records found." />; if (loading || !rows.length) return state;
    return <div className="ps-table-wrap"><table><thead><tr><th>Livestock</th><th>Event</th><th>Date</th><th>Status</th><th>Expected / Actual</th><th>Offspring</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><strong>{item.livestock_name}</strong><small>{item.animal_code}</small></td><td>{item.record_type}</td><td>{item.event_date}</td><td>{item.reproductive_status || "—"}</td><td><small>Expected: {item.expected_date || "—"}</small><small>Actual: {item.actual_date || "—"}</small></td><td>{item.alive_offspring}/{item.offspring_count}</td></tr>)}</tbody></table></div>;
}

function ProductionTable({ rows, loading, cropMode }) {
    const state = <TableState loading={loading} rows={rows} emptyText={cropMode ? "No crop harvest outputs found." : "No production records found."} />; if (loading || !rows.length) return state;
    return <div className="ps-table-wrap"><table><thead><tr><th>Source</th><th>Product</th><th>Date / Period</th><th>Produced</th><th>Farm Use</th><th>Loss</th><th>Reserved</th><th>Sold</th><th>Available</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><strong>{item.source_name}</strong><small>{item.source_type} • {item.source_code}</small></td><td>{item.output_type}</td><td><small>{item.period_start_date || item.record_date}</small><small>to {item.period_end_date || item.record_date}</small></td><td>{number(item.gross_quantity ?? item.quantity)} {item.unit}</td><td>{number(item.farm_use_quantity)} {item.unit}</td><td>{number(item.loss_quantity)} {item.unit}</td><td>{number(item.reserved_quantity)} {item.unit}</td><td>{number(item.sold_quantity)} {item.unit}</td><td className="ps-available">{number(item.available_quantity)} {item.unit}</td></tr>)}</tbody></table></div>;
}

function ProcessingTable({ rows, loading, canEdit, onVoid }) {
    const state = <TableState loading={loading} rows={rows} emptyText="No processing records found." />; if (loading || !rows.length) return state;
    return <div className="ps-table-wrap"><table><thead><tr><th>Livestock</th><th>Date</th><th>Head</th><th>Live Weight</th><th>Meat Output</th><th>Dressing Yield</th><th>Status</th><th>Actions</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><strong>{item.livestock_name}</strong><small>{item.animal_code}</small></td><td>{item.processing_date}</td><td>{item.animals_processed}</td><td>{item.live_weight_kg == null ? "—" : `${number(item.live_weight_kg)} kg`}</td><td>{number(item.meat_output_kg)} kg</td><td>{item.yield_percent == null ? "—" : `${number(item.yield_percent)}%`}</td><td className={item.is_voided ? "ps-voided-text" : "ps-available"}>{item.is_voided ? "Voided" : "Completed"}</td><td>{canEdit && <button className="ps-row-action danger" type="button" onClick={() => onVoid(item)} disabled={item.is_voided} title="Void processing"><span className="material-symbols-outlined">undo</span></button>}</td></tr>)}</tbody></table></div>;
}

function SalesTable({ rows, loading, canEdit, onDetails, onPayment, onReceipt, onVoid }) {
    const state = <TableState loading={loading} rows={rows} emptyText="No sales transactions found." />; if (loading || !rows.length) return state;
    return <div className="ps-table-wrap"><table><thead><tr><th>Invoice</th><th>Sources</th><th>Date</th><th>Items</th><th>Gross</th><th>Paid</th><th>Balance</th><th>Buyer</th><th>Actions</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><strong>{item.sale_code}</strong><small>{item.sale_type} • {item.payment_status}</small></td><td><strong>{(item.source_types || [item.source_type]).join(", ")}</strong><small>{item.source_name}</small></td><td>{item.sale_date}</td><td><strong>{item.item_count || 1} item{Number(item.item_count || 1) === 1 ? "" : "s"}</strong><small>{(item.items || []).slice(0, 2).map((line) => line.product_type).join(", ") || item.product_type}{Number(item.item_count || 1) > 2 ? "…" : ""}</small></td><td>{money(item.total_amount)}</td><td>{money(item.amount_paid)}</td><td className={Number(item.balance_due || 0) > 0 ? "ps-balance" : "ps-available"}>{money(item.balance_due)}</td><td>{item.buyer_name || "—"}</td><td><div className="ps-row-actions"><button className="ps-row-action" type="button" onClick={() => onDetails(item)} title="View invoice and payment history"><span className="material-symbols-outlined">visibility</span></button><button className="ps-row-action" type="button" onClick={() => onReceipt(item)} title="Receipt"><span className="material-symbols-outlined">receipt_long</span></button>{canEdit && !item.is_voided && Number(item.balance_due || 0) > 0 && <button className="ps-row-action" type="button" onClick={() => onPayment(item)} title="Record payment"><span className="material-symbols-outlined">payments</span></button>}{canEdit && <button className="ps-row-action danger" type="button" onClick={() => onVoid(item)} disabled={item.is_voided} title="Void sale"><span className="material-symbols-outlined">undo</span></button>}</div></td></tr>)}</tbody></table></div>;
}

function animalKind(animal) { return String(animal?.type || animal?.animalType || animal?.animal_type || "").toLowerCase(); }
function animalPurpose(animal) { return `${animal?.productionPurpose || animal?.production_purpose || ""} ${animal?.growthStatus || animal?.growth_status || ""}`.toLowerCase(); }
function isMeatAnimal(animal) { return ["meat", "meat production"].includes(String(animal?.productionPurpose || animal?.production_purpose || "").trim().toLowerCase()); }
function productionTypeFor(animal) {
    const type = animalKind(animal);
    const purpose = animalPurpose(animal);
    const females = Number(animal?.femaleQuantity ?? animal?.female_quantity ?? 0);
    const isBird = ["chicken", "duck", "bird", "poultry"].some((v) => type.includes(v));
    const eggEligible = ["egg", "laying", "layer", "breeding", "breeder"].some((v) => purpose.includes(v));
    if (isBird && females > 0 && eggEligible) return "Eggs";
    if (["goat", "cattle", "cow"].some((v) => type.includes(v)) && females > 0 && ["milk", "dairy", "lactat"].some((v) => purpose.includes(v))) return "Milk";
    return null;
}

function ProductionModal({ open, livestock, onClose, onSubmit, saving }) {
    const eligible = livestock.filter((animal) => productionTypeFor(animal));
    const [livestockId, setLivestockId] = useState("");
    const [periodStart, setPeriodStart] = useState(todayIso()); const [periodEnd, setPeriodEnd] = useState(todayIso());
    const [gross, setGross] = useState(""); const [loss, setLoss] = useState("0"); const [farmUse, setFarmUse] = useState("0"); const [reserved, setReserved] = useState("0");
    useEffect(() => { if (open) { setLivestockId(""); setGross(""); setLoss("0"); setFarmUse("0"); setReserved("0"); setPeriodStart(todayIso()); setPeriodEnd(todayIso()); } }, [open]);
    const selected = eligible.find((item) => item.id === Number(livestockId)); const outputType = productionTypeFor(selected) || "Eggs";
    const femaleCount = Number(selected?.femaleQuantity ?? selected?.female_quantity ?? 0); const days = Math.max(1, Math.floor((new Date(periodEnd) - new Date(periodStart)) / 86400000) + 1 || 1); const maxEggs = femaleCount * days;
    const saleable = Math.max(0, Number(gross || 0) - Number(loss || 0) - Number(farmUse || 0) - Number(reserved || 0));
    return <Modal open={open} title="Record Livestock Production" subtitle="Only eligible egg or milk producers appear. Meat is created only through Processing." onClose={onClose}><form className="ps-form" onSubmit={onSubmit}><div className="ps-form-grid">
        <Field label="Livestock"><select name="livestock_id" value={livestockId} onChange={(e) => setLivestockId(e.target.value)} required><option value="">Select eligible livestock</option>{eligible.map((animal) => <option key={animal.id} value={animal.id}>{animal.recordName} ({animal.animalId}) — {productionTypeFor(animal)}</option>)}</select></Field>
        <Field label="Output Type"><input name="output_type" value={selected ? outputType : "—"} readOnly /></Field>
        <Field label="Period Start"><input name="period_start_date" type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} required /></Field><Field label="Period End"><input name="period_end_date" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} required /></Field><Field label="Record Date"><input name="record_date" type="date" defaultValue={todayIso()} required /></Field>
        <Field label={outputType === "Eggs" ? "Active Laying Females" : "Animals Milked"}><input name="source_active_quantity" type="number" min="1" max={femaleCount || undefined} defaultValue={femaleCount || ""} required /></Field>
        <Field label="Gross Production"><input name="gross_quantity" type="number" min={outputType === "Eggs" ? "1" : "0.001"} step={outputType === "Eggs" ? "1" : "0.001"} max={outputType === "Eggs" && maxEggs > 0 ? maxEggs : undefined} value={gross} onChange={(e) => setGross(e.target.value)} required /></Field>
        <Field label="Damaged / Rejected"><input name="loss_quantity" type="number" min="0" step={outputType === "Eggs" ? "1" : "0.001"} value={loss} onChange={(e) => setLoss(e.target.value)} /></Field>
        <Field label="Farm Use"><input name="farm_use_quantity" type="number" min="0" step={outputType === "Eggs" ? "1" : "0.001"} value={farmUse} onChange={(e) => setFarmUse(e.target.value)} /></Field>
        <Field label="Reserved"><input name="reserved_quantity" type="number" min="0" step={outputType === "Eggs" ? "1" : "0.001"} value={reserved} onChange={(e) => setReserved(e.target.value)} /></Field>
        <Field label="Available for Sale"><input value={number(saleable)} readOnly /></Field><Field label="Unit"><input name="unit" value={outputType === "Eggs" ? "pcs" : "L"} readOnly /></Field><Field label="Quality / Grade"><input name="quality_grade" defaultValue="Grade A" /></Field>
    </div>{outputType === "Eggs" && selected && <div className="ps-help">Maximum for this period: {femaleCount} laying female(s) × {days} day(s) = {maxEggs} eggs.</div>}<Field label="Notes"><textarea name="notes" rows="3" /></Field><FormFooter onClose={onClose} label="Record Production" saving={saving} /></form></Modal>;
}

function ProcessingModal({ open, livestock, saving, onClose, onSubmit }) {
    const eligible = livestock.filter(isMeatAnimal);
    const [livestockId, setLivestockId] = useState(""); const selected = eligible.find((item) => item.id === Number(livestockId));
    useEffect(() => { if (open) setLivestockId(""); }, [open]);
    return <Modal open={open} title="Record Livestock Processing" subtitle="Only livestock designated for Meat production can be processed. The result becomes traceable meat stock." onClose={onClose}>{eligible.length === 0 ? <div className="ps-modal-empty"><span className="material-symbols-outlined">info</span><div><strong>No meat-production livestock is available.</strong><p>Open Livestock Management and set the correct Production Purpose to Meat before processing. Breeding and other purposes are protected.</p></div></div> : <form className="ps-form" onSubmit={onSubmit}><div className="ps-form-grid"><Field label="Meat Livestock"><select name="livestock_id" value={livestockId} onChange={(e) => setLivestockId(e.target.value)} required><option value="">Select meat-purpose livestock</option>{eligible.map((animal) => <option key={animal.id} value={animal.id}>{animal.recordName} ({animal.animalId}) — {animal.quantity} head</option>)}</select></Field><Field label="Processing Date"><input name="processing_date" type="date" defaultValue={todayIso()} required /></Field><Field label="Animals Processed"><input name="animals_processed" type="number" min="1" max={selected?.quantity || undefined} step="1" required /></Field><Field label="Total Live Weight (kg)"><input name="live_weight_kg" type="number" min="0.001" step="0.001" /></Field><Field label="Meat Output (kg)"><input name="meat_output_kg" type="number" min="0.001" step="0.001" required /></Field><Field label="Quality / Grade"><input name="quality_grade" defaultValue="Grade A" /></Field><Field label="Male Processed"><input name="male_quantity" type="number" min="0" max={selected?.maleQuantity || undefined} defaultValue="0" /></Field><Field label="Female Processed"><input name="female_quantity" type="number" min="0" max={selected?.femaleQuantity || undefined} defaultValue="0" /></Field><Field label="Unknown Sex Processed"><input name="unknown_quantity" type="number" min="0" max={selected?.unknownSexQuantity || undefined} defaultValue="0" /></Field></div><div className="ps-help">Only healthy animals can be processed. Meat output cannot exceed total live weight. Saving reduces the live head count and creates one meat production lot.</div><Field label="Notes"><textarea name="notes" rows="3" /></Field><FormFooter onClose={onClose} label="Record Processing" saving={saving} /></form>}</Modal>;
}

function SaleModal({ open, scope, livestock, production, inventory, sourceLoading, sourceError, onRetry, saving, onClose, onSubmit }) {
    const [kind, setKind] = useState("Production");
    const [sourceId, setSourceId] = useState("");
    const [sourceQuery, setSourceQuery] = useState("");
    const [quantity, setQuantity] = useState("");
    const [unitPrice, setUnitPrice] = useState("");
    const [male, setMale] = useState("0");
    const [female, setFemale] = useState("0");
    const [unknown, setUnknown] = useState("0");
    const [items, setItems] = useState([]);
    const [saleDate, setSaleDate] = useState(todayIso());
    const [buyer, setBuyer] = useState("");
    const [paymentStatus, setPaymentStatus] = useState("Paid");
    const [paymentMethod, setPaymentMethod] = useState("Cash");
    const [amountPaid, setAmountPaid] = useState("");
    const [notes, setNotes] = useState("");

    useEffect(() => {
        if (!open) return;
        setKind("Production"); setSourceId(""); setSourceQuery(""); setQuantity(""); setUnitPrice("");
        setMale("0"); setFemale("0"); setUnknown("0"); setItems([]);
        setSaleDate(todayIso()); setBuyer(""); setPaymentStatus("Paid");
        setPaymentMethod("Cash"); setAmountPaid(""); setNotes("");
    }, [open, scope]);

    const sourceOptions = useMemo(() => {
        if (sourceLoading || sourceError) return [];
        return kind === "Production" ? production
            : kind === "Live Animal" ? livestock.filter((item) => Number(item.quantity || 0) > 0)
                : inventory;
    }, [kind, production, livestock, inventory, sourceLoading, sourceError]);
    const selected = useMemo(() => sourceOptions.find((item) => item.id === Number(sourceId)), [sourceOptions, sourceId]);
    const visibleSources = useMemo(() => {
        const query = sourceQuery.trim().toLowerCase();
        const matches = query ? sourceOptions.filter((item) => (
            `${item.source_name || item.recordName || item.name || ""} ${item.source_code || item.animalId || item.itemCode || ""} ${item.output_type || ""}`
        ).toLowerCase().includes(query)) : sourceOptions;
        const first = matches.slice(0, 150);
        if (selected && !first.some((item) => item.id === selected.id)) first.unshift(selected);
        return first;
    }, [sourceOptions, sourceQuery, selected]);
    const sourceOptionElements = useMemo(() => visibleSources.map((item) => <option key={item.id} value={item.id}>{kind === "Production" ? `${item.source_type} • ${item.source_name} • ${item.output_type} — ${number(item.available_quantity)} ${item.unit}` : kind === "Live Animal" ? `${item.recordName} (${item.animalId}) — ${item.quantity} head` : `${item.name} (${item.itemCode}) — ${number(item.quantity)} ${item.unit}`}</option>), [visibleSources, kind]);
    const available = kind === "Production" ? Number(selected?.available_quantity || 0) : Number(selected?.quantity || 0);
    const unit = kind === "Production" ? selected?.unit : kind === "Live Animal" ? "head" : selected?.unit;
    const sourceName = kind === "Production" ? `${selected?.source_name || ""} — ${selected?.output_type || ""}` : kind === "Live Animal" ? selected?.recordName : selected?.name;
    const sourceCode = kind === "Production" ? selected?.source_code : kind === "Live Animal" ? selected?.animalId : selected?.itemCode;

    const chooseSource = (value) => {
        setSourceId(value); setQuantity(""); setMale("0"); setFemale("0"); setUnknown("0");
        const next = sourceOptions.find((item) => item.id === Number(value));
        setUnitPrice(kind === "Inventory" && next ? String(next.price || "") : "");
    };
    const changeKind = (value) => { setKind(value); setSourceId(""); setSourceQuery(""); setQuantity(""); setUnitPrice(""); setMale("0"); setFemale("0"); setUnknown("0"); };
    const addItem = () => {
        const qty = Number(quantity);
        const price = Number(unitPrice);
        if (!selected || !Number.isFinite(qty) || qty <= 0 || qty > available) { notifyError(`Enter a quantity between 0 and ${number(available)} ${unit || "units"}.`, "Invalid Sale Item"); return; }
        if (kind === "Live Animal" && !Number.isInteger(qty)) { notifyError("Live-animal quantity must be a whole number.", "Invalid Sale Item"); return; }
        if (!Number.isFinite(price) || price < 0) { notifyError("Enter a valid unit price.", "Invalid Sale Item"); return; }
        const identity = `${kind}:${selected.id}`;
        if (items.some((item) => item.identity === identity)) { notifyError("That stock source is already on this invoice. Remove or edit the existing line first.", "Duplicate Item"); return; }
        const item = {
            identity,
            item_kind: kind,
            production_record_id: kind === "Production" ? selected.id : null,
            livestock_id: kind === "Live Animal" ? selected.id : null,
            inventory_item_id: kind === "Inventory" ? selected.id : null,
            quantity: qty,
            unit,
            unit_price: price,
            male_quantity: kind === "Live Animal" ? Number(male || 0) : 0,
            female_quantity: kind === "Live Animal" ? Number(female || 0) : 0,
            unknown_quantity: kind === "Live Animal" ? Number(unknown || 0) : 0,
            displayName: sourceName,
            sourceCode,
        };
        const sexTotal = item.male_quantity + item.female_quantity + item.unknown_quantity;
        if (kind === "Live Animal" && sexTotal !== 0 && sexTotal !== qty) { notifyError("Male, female, and unknown quantities must total the animals on this line.", "Invalid Sex Breakdown"); return; }
        setItems((current) => [...current, item]);
        setSourceId(""); setQuantity(""); setUnitPrice(""); setMale("0"); setFemale("0"); setUnknown("0");
    };
    const invoiceTotal = items.reduce((total, item) => total + item.quantity * item.unit_price, 0);
    const submit = (event) => {
        event.preventDefault();
        if (!items.length) { notifyError("Add at least one item before saving the sale.", "Empty Invoice"); return; }
        const paid = Number(amountPaid || 0);
        if (paymentStatus === "Partial" && (!paid || paid >= invoiceTotal)) { notifyError("A partial payment must be greater than zero and less than the invoice total.", "Invalid Payment"); return; }
        onSubmit({
            sale_type: "Multi-item",
            sale_date: saleDate,
            items: items.map((item) => ({
                item_kind: item.item_kind,
                production_record_id: item.production_record_id,
                livestock_id: item.livestock_id,
                inventory_item_id: item.inventory_item_id,
                quantity: item.quantity,
                unit: item.unit,
                unit_price: item.unit_price,
                male_quantity: item.male_quantity,
                female_quantity: item.female_quantity,
                unknown_quantity: item.unknown_quantity,
            })),
            buyer_name: buyer.trim() || null,
            payment_status: paymentStatus,
            amount_paid: paymentStatus === "Partial" ? paid : paymentStatus === "Unpaid" ? 0 : null,
            payment_method: paymentStatus === "Unpaid" ? null : paymentMethod || null,
            notes: notes.trim() || null,
        });
    };

    return <Modal open={open} className="ps-sale-modal" title="Create Sales Invoice" subtitle="Add crop harvests, eggs, meat, live livestock, and saleable inventory products to one transaction." onClose={onClose}><form className="ps-form ps-sale-form" onSubmit={submit}>
        <div className="ps-sale-layout">
        <section className="ps-sale-builder ps-sale-item-builder"><div className="ps-section-heading"><div><h3>Add Invoice Item</h3><p>Only currently available, traceable stock can be added.</p></div><span>{items.length} item{items.length === 1 ? "" : "s"}</span></div>
            {sourceLoading && <p className="ps-source-status" role="status">Loading available stock… You can enter customer details while it loads.</p>}
            {sourceError && <div className="ps-source-status ps-source-error" role="alert"><span>{sourceError}</span><button type="button" className="ps-secondary" onClick={onRetry}>Retry stock loading</button></div>}
            <div className="ps-form-grid">
                <Field label="Stock Type"><select value={kind} onChange={(event) => changeKind(event.target.value)} disabled={sourceLoading || Boolean(sourceError)}><option value="Production">Crop / Egg / Meat / Milk Output</option><option value="Live Animal">Live Livestock</option><option value="Inventory">Other Saleable Inventory Product</option></select></Field>
                <Field label="Search Available Stock"><input value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} placeholder="Search name or code" disabled={sourceLoading || Boolean(sourceError)} /></Field>
                <Field label="Available Source"><select value={sourceId} onChange={(event) => chooseSource(event.target.value)} disabled={sourceLoading || Boolean(sourceError)}><option value="">Select available stock</option>{sourceOptionElements}</select></Field>
                <Field label="Available"><input value={selected ? `${number(available)} ${unit}` : "—"} readOnly /></Field>
                <Field label="Quantity"><input type="number" min={kind === "Live Animal" ? "1" : "0.001"} step={kind === "Live Animal" ? "1" : "0.001"} max={available || undefined} value={quantity} onChange={(event) => setQuantity(event.target.value)} /></Field>
                <Field label={`Price per ${unit || "unit"}`}><input type="number" min="0" step="0.01" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} /></Field>
                {kind === "Live Animal" && <><Field label="Male Sold"><input type="number" min="0" value={male} onChange={(event) => setMale(event.target.value)} /></Field><Field label="Female Sold"><input type="number" min="0" value={female} onChange={(event) => setFemale(event.target.value)} /></Field><Field label="Unknown Sex Sold"><input type="number" min="0" value={unknown} onChange={(event) => setUnknown(event.target.value)} /></Field></>}
            </div>
            {sourceOptions.length > visibleSources.length && <p className="ps-source-status">Showing {visibleSources.length} of {sourceOptions.length} available sources. Search by name or code to find another.</p>}
            <div className="ps-add-line"><button type="button" className="ps-secondary" onClick={addItem} disabled={!selected}><span className="material-symbols-outlined">add</span>Add to Invoice</button></div>
        </section>
        <section className="ps-invoice-lines ps-invoice-preview"><div className="ps-section-heading"><div><h3>Invoice Items</h3><p>Stock is deducted only when the complete invoice saves successfully.</p></div><strong>{money(invoiceTotal)}</strong></div>{items.length === 0 ? <EmptyState text="No items added yet." /> : items.map((item, index) => <article key={item.identity}><span>{index + 1}</span><div><strong>{item.displayName}</strong><small>{item.item_kind} • {item.sourceCode || "No code"}</small><small>{number(item.quantity)} {item.unit} × {money(item.unit_price)} each</small></div><b>{money(item.quantity * item.unit_price)}</b><button type="button" onClick={() => setItems((current) => current.filter((line) => line.identity !== item.identity))} aria-label={`Remove ${item.displayName}`}><span className="material-symbols-outlined">delete</span></button></article>)}</section>
        <section className="ps-sale-builder ps-sale-payment"><div className="ps-section-heading"><div><h3>Customer &amp; Payment</h3><p>Payments are tracked against the whole invoice and remain in history.</p></div></div><div className="ps-form-grid"><Field label="Sale Date"><input type="date" value={saleDate} onChange={(event) => setSaleDate(event.target.value)} required /></Field><Field label="Buyer / Customer"><input value={buyer} onChange={(event) => setBuyer(event.target.value)} placeholder="Walk-in customer if blank" /></Field><Field label="Payment Status"><select value={paymentStatus} onChange={(event) => setPaymentStatus(event.target.value)}><option>Paid</option><option>Partial</option><option>Unpaid</option></select></Field>{paymentStatus !== "Unpaid" && <Field label="Payment Method"><select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option>Cash</option><option>GCash</option><option>Bank Transfer</option><option>Other</option></select></Field>}{paymentStatus === "Partial" && <Field label="Amount Paid"><input type="number" min="0.01" max={invoiceTotal || undefined} step="0.01" value={amountPaid} onChange={(event) => setAmountPaid(event.target.value)} required /></Field>}</div><Field label="Notes"><textarea rows="3" value={notes} onChange={(event) => setNotes(event.target.value)} /></Field></section>
        </div>
        <FormFooter onClose={onClose} label={`Save Invoice • ${money(invoiceTotal)}`} saving={saving} />
    </form></Modal>;
}

function PaymentModal({ open, sale, saving, onClose, onSubmit }) {
    return <Modal open={open} title="Record Sale Payment" subtitle={sale ? `${sale.sale_code} • Outstanding balance ${money(sale.balance_due)}` : "Record a collection against an existing sale."} onClose={onClose}><form className="ps-form" onSubmit={onSubmit}><div className="ps-form-grid"><Field label="Payment Date"><input name="payment_date" type="date" defaultValue={todayIso()} required /></Field><Field label="Amount"><input name="amount" type="number" min="0.01" max={sale?.balance_due || undefined} step="0.01" required /></Field><Field label="Payment Method"><select name="payment_method"><option>Cash</option><option>GCash</option><option>Bank Transfer</option><option>Other</option></select></Field></div><Field label="Notes"><textarea name="notes" rows="3" /></Field><FormFooter onClose={onClose} label="Save Payment" saving={saving} /></form></Modal>;
}

function SaleDetailsModal({ open, sale, payments, canEdit, onClose, onPayment, onReceipt }) {
    if (!sale) return null;
    return <Modal open={open} title={`Invoice ${sale.sale_code}`} subtitle={`${sale.sale_date} • ${sale.buyer_name || "Walk-in customer"} • ${sale.payment_status}`} onClose={onClose}><div className="ps-sale-details"><section><div className="ps-section-heading"><div><h3>Items Sold</h3><p>Each line remains linked to its original crop, livestock, production, or inventory record.</p></div><strong>{money(sale.total_amount)}</strong></div><div className="ps-detail-table"><div className="head"><span>Product / Source</span><span>Quantity</span><span>Price</span><span>Amount</span></div>{(sale.items || []).map((item) => <div key={item.id || item.line_number}><span><strong>{item.product_type}</strong><small>{item.source_type} • {item.source_name} • {item.source_code || "No code"}</small></span><span>{number(item.quantity)} {item.unit}</span><span>{money(item.unit_price)}</span><span>{money(item.line_total)}</span></div>)}</div></section><section><div className="ps-section-heading"><div><h3>Payment History</h3><p>Partial collections are never replaced or hidden.</p></div><span className={Number(sale.balance_due || 0) > 0 ? "ps-balance" : "ps-available"}>{money(sale.balance_due)} due</span></div>{payments.length === 0 ? <EmptyState text="No payment has been recorded." /> : <div className="ps-payment-history">{payments.map((payment) => <article key={payment.id}><div><strong>{payment.payment_date}</strong><small>{payment.payment_method || "Not specified"} • {payment.recorded_by_name || "System user"}</small>{payment.notes && <small>{payment.notes}</small>}</div><b>{money(payment.amount)}</b></article>)}</div>}</section>{sale.is_voided && <div className="ps-void-notice"><strong>Voided transaction</strong><span>{sale.void_reason}</span></div>}</div><footer className="ps-modal-footer"><button type="button" className="ps-secondary" onClick={onReceipt}><span className="material-symbols-outlined">receipt_long</span>Receipt</button>{canEdit && !sale.is_voided && Number(sale.balance_due || 0) > 0 && <button type="button" className="ps-primary" onClick={onPayment}><span className="material-symbols-outlined">payments</span>Record Payment</button>}<button type="button" className="ps-secondary" onClick={onClose}>Close</button></footer></Modal>;
}

export default ProductionSales;
