import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { inventoryService } from "../src/services/inventoryService.js";
import { invalidateReadCache, ApiError } from "../src/services/httpClient.js";
import { stableIdempotencyKey, clearStableIdempotencyKey } from "../src/services/idempotencyKey.js";
const require = createRequire(import.meta.url), parser = require("next/dist/compiled/babel/parser");
const paths = { modal: "src/components/InventoryModals/InventoryModals.jsx", history: "src/hooks/useInventoryStockHistory.js", page: "src/views/Inventory/hooks/useInventoryPage.js", choices: "src/hooks/useResourceChoices.js" };
function callback(context, path, name) {
    const code=fs.readFileSync(new URL(`../${path}`,import.meta.url),"utf8"), tree=parser.parse(code,{sourceType:"module",plugins:["jsx"]});
    let found;
    function visit(node) { if(!node || typeof node!=="object" || found)return;
        if(node.type==="VariableDeclarator" && node.id?.name===name) { found=node.init.type==="CallExpression" ? node.init.arguments[0] : node.init;return; }
        for(const value of Object.values(node)) { if(Array.isArray(value))value.forEach(visit);else if(value?.type)visit(value); }
    }
    visit(tree);assert.ok(found,name);
    return new vm.Script(`(${code.slice(found.start,found.end)})`).runInContext(context);
}
function context(initial, extra={}) {
    const value={...initial,...extra,AbortController};
    for(const name of Object.keys(initial))value[`set${name[0].toUpperCase()+name.slice(1)}`]=next=>{value[name]=typeof next==="function"?next(value[name]):next;if(name==="page" && value.pageRef)value.pageRef.current=value.page;};
    return vm.createContext(value);
}
const gate=()=>{let resolve;const promise=new Promise(yes=>{resolve=yes;});return{promise,resolve};};
function stockContext(save) {
    const item={id:7,quantity:100,editVersion:1,unit:"kg",supplier:"Test"};
    return context({adjustmentForm:{type:"Set Exact Quantity",quantity:"95",date:"2026-11-13",reason:"Physical count",reference:"Ref",supplier:"Test"},adjustmentSaving:false,stockSnapshot:item,activeTab:"adjust"},{
        item,stockItem:item,adjustmentSubmittingRef:{current:false},adjustmentRequestRef:{current:null},
        notify:()=>{},stableIdempotencyKey,clearStableIdempotencyKey,getTodayDate:()=>"2026-11-13",onAdjustStock:save,
        stockConflict:{handleError:()=>true},
    });
}
test("an exact-stock conflict keeps entries and retry identity until latest balance is reviewed",async()=>{
    const calls=[];const ctx=stockContext(async(...args)=>{calls.push(args);throw new ApiError("Changed stock",{status:409,code:"RECORD_CONFLICT"});});
    const submit=callback(ctx,paths.modal,"handleAdjustmentSubmit"), before=JSON.stringify(ctx.adjustmentForm);
    await submit({preventDefault(){}});
    assert.equal(JSON.stringify(ctx.adjustmentForm),before);assert.equal(ctx.activeTab,"adjust");assert.equal(ctx.stockSnapshot.editVersion,1);
    assert.equal(calls[0][1].editVersion,1);assert.equal(ctx.adjustmentSaving,false);
    const firstKey=calls[0][2];assert.ok(firstKey);
    ctx.stockItem={...ctx.stockItem,quantity:70,editVersion:2};
    ctx.onAdjustStock=async(...args)=>{calls.push(args);return{id:7,quantity:95,editVersion:3};};
    await submit({preventDefault(){}});
    assert.equal(calls[1][1].editVersion,2);assert.equal(calls[1][1].quantity,95);assert.notEqual(calls[1][2],firstKey);
    assert.equal(ctx.stockSnapshot.editVersion,3);assert.equal(ctx.activeTab,"history");
});
test("a slow stock save accepts only one request and releases its immediate guard",async()=>{
    const pending=gate();let calls=0;const ctx=stockContext(()=>{calls++;return pending.promise;});
    const submit=callback(ctx,paths.modal,"handleAdjustmentSubmit");
    const first=submit({preventDefault(){}});await submit({preventDefault(){}});
    assert.equal(calls,1);assert.equal(ctx.adjustmentSaving,true);
    pending.resolve(false);await first;assert.equal(ctx.adjustmentSubmittingRef.current,false);assert.equal(ctx.adjustmentSaving,false);
});
function historyContext(service) {
    return context({page:{key:"",items:[],total:0,snapshot:null},loading:false,error:""},{active:true,inventoryId:7,key:"record7",pageRef:{current:{key:"",items:[],total:0,snapshot:null}},sequence:{current:0},controller:{current:null},busy:{current:false},failedOffset:{current:0},inventoryService:{getStockHistoryPage:service}});
}
test("history next-page retry retains successful rows and reuses the snapshot",async()=>{
    let fail=true;const calls=[];
    const ctx=historyContext(async(id,query)=>{calls.push(query);if(query.offset && fail)throw new Error("History offline");return{items:query.offset?[{id:2}]:[{id:1}],total:2,snapshot_id:42};});
    const load=callback(ctx,paths.history,"load");await load();await load(1);
    assert.equal(ctx.page.items.length,1);assert.equal(ctx.error,"History offline");assert.equal(ctx.failedOffset.current,1);
    fail=false;await load(ctx.failedOffset.current);
    assert.equal(ctx.page.items.length,2);assert.equal(calls[1].snapshot_id,42);assert.equal(calls[2].snapshot_id,42);assert.equal(ctx.error,"");
});
test("a new history record cancels the obsolete page and ignores its late result",async()=>{
    const pending=gate(),calls=[];const ctx=historyContext(async(id,query)=>{calls.push(query);return id===7?pending.promise:{items:[{id:20}],total:1,snapshot_id:20};});
    const load=callback(ctx,paths.history,"load"),old=load();ctx.inventoryId=8;ctx.key="record8";await load();
    assert.equal(calls[0].signal.aborted,true);pending.resolve({items:[{id:1}],total:100,snapshot_id:100});await old;
    assert.equal(ctx.page.items[0].id,20);assert.equal(ctx.page.key,"record8");assert.equal(ctx.loading,false);
});
test("history does not request closed panels and treats successful empty history as loaded",async()=>{
    let calls=0;const ctx=historyContext(async()=>{calls++;return{items:[],total:0,snapshot_id:0};});const load=callback(ctx,paths.history,"load");
    ctx.active=false;await load();assert.equal(calls,0);ctx.active=true;await load();assert.equal(ctx.page.total,0);assert.equal(ctx.page.key,"record7");assert.equal(ctx.error,"");
});
function pageContext(record, read=async()=>{throw new Error("Unexpected metadata request");}) {
    const item={id:7,name:"Original",editVersion:1,quantity:100,stockHistory:[]};
    return context({inventory:[item],selectedItem:item},{inventoryService:{addStockAdjustment:async()=>record,getInventoryItem:read},notify:()=>{},isRecordEditConflict:error=>error.code==="RECORD_CONFLICT",loadInventory:async()=>{},loadSummary:async()=>{}});
}
test("a fresh stock save merges its result without another read",async()=>{
    const ctx=pageContext({id:40,newQuantity:105,inventoryEditVersion:2,inventoryPreviousEditVersion:1});
    const result=await callback(ctx,paths.page,"handleAdjustStock")(7,{type:"Restock"},"key");
    assert.equal(result.quantity,105);assert.equal(ctx.selectedItem.editVersion,2);assert.equal(ctx.inventory[0].quantity,105);
});
test("a fresh detail snapshot replaces older list metadata when merging a stock save",async()=>{
    const ctx=pageContext({id:40,newQuantity:105,inventoryEditVersion:4,inventoryPreviousEditVersion:3});
    ctx.selectedItem={id:7,name:"Updated detail name",supplier:"Updated supplier",editVersion:3,quantity:100,unit:"kg"};
    await callback(ctx,paths.page,"handleAdjustStock")(7,{type:"Restock"},"key");
    assert.equal(ctx.inventory[0].name,"Updated detail name");assert.equal(ctx.inventory[0].supplier,"Updated supplier");assert.equal(ctx.inventory[0].editVersion,4);
});
test("a stock replay or changed metadata reloads current fields before assigning a version",async()=>{
    for(const record of [{id:40,newQuantity:105},{id:40,newQuantity:105,inventoryEditVersion:4,inventoryPreviousEditVersion:3}]) {
        let reads=0;const latest={id:7,name:"Changed by another clerk",quantity:120,editVersion:5};
        const ctx=pageContext(record,async()=>{reads++;return latest;});
        const result=await callback(ctx,paths.page,"handleAdjustStock")(7,{type:"Restock"},"key");
        assert.equal(reads,1);assert.equal(result.quantity,120);assert.equal(result.name,latest.name);assert.equal(ctx.selectedItem.editVersion,5);
    }
});
test("failed metadata reads cannot bless old fields or replace a balance with a historical replay",async()=>{
    for(const record of [{id:40,newQuantity:105,inventoryEditVersion:4,inventoryPreviousEditVersion:3},{id:40,newQuantity:105}]) {
        const ctx=pageContext(record);
        const result=await callback(ctx,paths.page,"handleAdjustStock")(7,{type:"Restock"},"key");
        assert.equal(result.editVersion,undefined);assert.equal(ctx.selectedItem.editVersion,undefined);
        assert.equal(result.quantity,record.inventoryEditVersion?105:100);
    }
});
const originals=Object.fromEntries(["window","sessionStorage","localStorage","fetch"].map(key=>[key,globalThis[key]]));
function browser(){invalidateReadCache();globalThis.window={location:{origin:"http://localhost:3000"},setTimeout,clearTimeout,dispatchEvent(){}};globalThis.sessionStorage=globalThis.localStorage={getItem:()=>null};}
test.after(()=>Object.assign(globalThis,originals));
test("exact stock API requests send the original version and block missing versions locally",async()=>{
    browser();const calls=[];globalThis.fetch=async(url,options)=>{calls.push({url,options});return Response.json({id:2,new_quantity:95,inventory_edit_version:2,inventory_previous_edit_version:1});};
    const data={type:"Set Exact Quantity",quantity:95,date:"2026-11-13",reason:"Count",editVersion:1};
    const saved=await inventoryService.addStockAdjustment(7,data,{idempotencyKey:"exact-key"});
    assert.equal(JSON.parse(calls[0].options.body).expected_version,1);assert.equal(saved.inventoryEditVersion,2);
    assert.equal(calls[0].options.headers["Idempotency-Key"],"exact-key");
    await assert.rejects(inventoryService.addStockAdjustment(7,{...data,editVersion:undefined}),{status:428});assert.equal(calls.length,1);
});
test("metadata and paged history transport bypass cache without downloading embedded history",async()=>{
    browser();const calls=[];globalThis.fetch=async(url,options)=>{calls.push({url:new URL(url),options});return String(url).includes("stock-history")?Response.json({items:[{id:4,new_quantity:12}],total:30,snapshot_id:99}):Response.json({id:7,edit_version:2,stock_history:[]});};
    await inventoryService.getInventoryItem(7);const page=await inventoryService.getStockHistoryPage(7,{offset:25,snapshot_id:99});
    assert.equal(calls[0].url.searchParams.get("include_history"),"false");assert.equal(calls[0].options.cache,"no-store");
    assert.equal(calls[1].url.searchParams.get("limit"),"25");assert.equal(calls[1].url.searchParams.get("snapshot_id"),"99");assert.equal(page.items[0].newQuantity,12);
});
