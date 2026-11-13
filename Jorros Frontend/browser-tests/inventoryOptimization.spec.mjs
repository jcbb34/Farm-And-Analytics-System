import { test, expect } from "@playwright/test";
import { serveSessionPolicy } from "./helpers/serveSessionPolicy.mjs";
const profile={id:1,username:"stock.test",fullName:"Stock Tester",role:"System Administrator",permissions:["*"],status:"Active"};
const initial={id:7,item_code:"INV-TEST",name:"Test Feed",category:"Feed",quantity:100,unit:"kg",reorder_level:5,cost:1,price:1,supplier:"Test",date_acquired:"2026-11-13",location:"Store",edit_version:1,is_archived:false};
async function setup(page,{choiceFailure=false,historyFailure=false}={}) {
    const state={item:{...initial},writes:[],metadataReads:[],history:[],choices:[],historyFailure,choiceFailure,bulkReads:0};
    await page.addInitScript(user=>sessionStorage.setItem("joross-auth",JSON.stringify({accessToken:"synthetic-stock-token",user,expiresAt:Date.now()+3600000})),profile);
    await page.route("**/api/v1/**",async route=>{
        if(await serveSessionPolicy(route,page))return;
        const request=route.request(),url=new URL(request.url()),path=url.pathname.replace(/^\/api\/v1/,"");
        if(path==="/auth/me")return route.fulfill({json:profile});
        if(path==="/events/stream")return route.fulfill({status:503,json:{}});
        if(path==="/inventory/page")return route.fulfill({json:{items:[state.item],total:1}});
        if(path==="/inventory/summary")return route.fulfill({json:{total:1,in_stock:1,low_stock:0,out_of_stock:0,total_value:100,categories:["Feed"],suppliers:["Test"]}});
        if(path==="/inventory/movements/summary")return route.fulfill({json:[]});
        if(path==="/inventory/7"){state.metadataReads.push(url.searchParams.get("include_history"));return route.fulfill({json:{...state.item,stock_history:[],stock_history_included:false}});}
        if(path==="/inventory/7/stock-adjustments"){
            const body=request.postDataJSON();state.writes.push(body);
            if(state.writes.length===1){state.item={...state.item,quantity:70,edit_version:2};return route.fulfill({status:409,headers:{"X-Record-Conflict":"RECORD_CONFLICT"},json:{detail:"Stock changed while this form was open. Review the latest balance."}});}
            state.item={...state.item,quantity:body.quantity,edit_version:3};return route.fulfill({status:201,json:{id:80,new_quantity:body.quantity,previous_quantity:70,inventory_edit_version:3,inventory_previous_edit_version:2}});
        }
        if(path==="/inventory/7/stock-history"){
            state.history.push(Object.fromEntries(url.searchParams));
            if(state.historyFailure){state.historyFailure=false;return route.fulfill({status:503,json:{detail:"History temporarily unavailable"}});}
            const offset=Number(url.searchParams.get("offset")||0);
            return route.fulfill({json:{items:Array.from({length:Math.min(25,63-offset)},(_,i)=>({id:63-offset-i,adjustment_type:"Restock",quantity:1,previous_quantity:0,new_quantity:1,adjustment_date:"2026-11-13",reason:`Movement ${63-offset-i}`})),total:63,snapshot_id:63,offset,limit:25}});
        }
        if(path==="/inventory/choices"){
            state.choices.push(Object.fromEntries(url.searchParams));
            if(state.choiceFailure){state.choiceFailure=false;return route.fulfill({status:503,json:{detail:"Feed choices temporarily unavailable"}});}
            let rows=Array.from({length:61},(_,i)=>({id:i+1,name:`Feed ${String(i+1).padStart(3,"0")}`,category:"Feed",unit:"kg",quantity:100}));
            const selected=rows.find(row=>String(row.id)===url.searchParams.get("selected_id"))||null;
            const search=url.searchParams.get("search")||"";rows=rows.filter(row=>row.name.toLowerCase().includes(search.toLowerCase()));
            const offset=Number(url.searchParams.get("offset")||0);
            return route.fulfill({json:{items:rows.slice(offset,offset+25),total:rows.length,selected}});
        }
        if(path==="/display/livestock")return route.fulfill({json:{items:[],total:0}});
        if(path==="/display/livestock/overview")return route.fulfill({json:{records:0,total:0,healthy:0,risk:0,types:[],pens:[],health_counts:{},analytics:{population:{},age_groups:{},planned_feed:{},estimated_monthly_budget:0}}});
        if(path==="/display/livestock/chart")return route.fulfill({json:{items:[]}});
        if(path==="/inventory"){state.bulkReads++;return route.fulfill({json:[]});}
        if(path.endsWith("/calendar/config"))return route.fulfill({json:{today:"2026-11-13",timezone:"Asia/Manila"}});
        return route.fulfill({json:[]});
    });return state;
}
async function openInventory(page){await page.goto("/inventory");await page.getByTitle("View inventory",{exact:true}).click();return page.locator(".inventory-details-modal");}
test("exact stock conflict preserves entries and saves only after reviewing current balance",async({page})=>{
    const state=await setup(page),dialog=await openInventory(page);
    await dialog.getByRole("button",{name:"Adjust Stock",exact:true}).click();
    await dialog.getByLabel("Adjustment Type").selectOption("Set Exact Quantity");
    await dialog.locator("#stockAdjustmentQuantity").fill("95");await dialog.locator("#stockAdjustmentReason").fill("Physical count checked");
    await dialog.getByRole("button",{name:"Save Stock Adjustment",exact:true}).click();
    await expect(dialog.getByText("Record updated elsewhere",{exact:true})).toBeVisible();
    await expect(dialog.locator("#stockAdjustmentQuantity")).toHaveValue("95");await expect(dialog.locator("#stockAdjustmentReason")).toHaveValue("Physical count checked");
    await dialog.getByRole("button",{name:"Reload latest record",exact:true}).click();
    await expect(dialog.getByText("Current balance for this adjustment:")).toContainText("70 kg");
    await dialog.getByRole("button",{name:"Save Stock Adjustment",exact:true}).click();
    await expect(dialog.getByRole("heading",{name:"Stock Movement History"})).toBeVisible();
    expect(state.writes.map(row=>row.expected_version)).toEqual([1,2]);expect(state.metadataReads.every(value=>value==="false")).toBe(true);
});
test("history failure retries and older pages keep accurate counts",async({page})=>{
    const state=await setup(page,{historyFailure:true}),dialog=await openInventory(page);
    expect(state.history).toHaveLength(0);await dialog.getByRole("button",{name:"Stock History",exact:true}).click();
    await expect(dialog.getByText("History temporarily unavailable",{exact:true})).toBeVisible();
    await dialog.getByRole("button",{name:"Retry history",exact:true}).click();
    await expect(dialog.getByText("25 of 63 records",{exact:true})).toBeVisible();
    await dialog.getByRole("button",{name:"Load older movements",exact:true}).click();
    await expect(dialog.getByText("50 of 63 records",{exact:true})).toBeVisible();expect(state.history.at(-1).snapshot_id).toBe("63");
});
test("Livestock feed choices retry and search records beyond the first page",async({page})=>{
    const state=await setup(page,{choiceFailure:true});await page.goto("/livestock");
    await page.getByRole("button",{name:"Add Livestock",exact:true}).click();
    await expect(page.getByText("Feed choices temporarily unavailable",{exact:false})).toBeVisible();
    await page.getByRole("button",{name:"Retry choices",exact:true}).click();
    await expect(page.getByText("25 of 61 matching choices",{exact:true})).toBeVisible();
    await page.getByRole("searchbox",{name:"Search feed inventory",exact:true}).fill("Feed 061");
    await expect(page.getByText("1 of 1 matching choices",{exact:true})).toBeVisible();
    await page.getByLabel("Feed Item",{exact:true}).selectOption("61");
    await expect(page.getByLabel("Feed Item",{exact:true})).toHaveValue("61");expect(state.bulkReads).toBe(0);
});
