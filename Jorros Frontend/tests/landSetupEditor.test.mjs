import test from 'node:test';
import assert from 'node:assert/strict';
import { emptyLandEditor, existingLandName, usableMeasuredArea, validateLandEditor } from '../src/components/CropPlanning/landSetupEditor.js';

const land = { total_area_m2:18000, fields:[
    {id:1,name:'Field A — Coconut Plantation',area_m2:null,unavailable_area_m2:0,sections:[
        {id:10,name:'Section A1',area_m2:null,unavailable_area_m2:0,edit_version:1},
    ]},
    {id:2,name:'Field B — Banana Plantation',area_m2:1400,unavailable_area_m2:100,sections:[
        {id:20,name:'Section B1',area_m2:700,unavailable_area_m2:0,edit_version:2},
        {id:21,name:'Section B2',area_m2:500,unavailable_area_m2:0,edit_version:1},
    ]},
]};
const check = (type,parentId,editingId,overrides) => validateLandEditor({land,type,parentId,editingId,
    form:{...emptyLandEditor,name:'Section New',...overrides}});

test('creating duplicate section is blocked before POST',()=>{
    assert.match(check('section','1',null,{name:'  SECTION A1  '}),/already exists/);
});
test('editing the same section does not trigger duplicate check',()=>{
    assert.equal(check('section','1',10,{name:'Section A1'}),'');
});
test('different fields can use the same section name',()=>{
    assert.equal(check('section','2',null,{name:'Section A1'}),'');
});
test('creating duplicate field is blocked',()=>{
    assert.ok(existingLandName(land,{type:'field',name:'FIELD B — BANANA PLANTATION'}));
    assert.match(check('field','',null,{name:'FIELD B — BANANA PLANTATION'}),/already exists/);
});
test('cannot measure section before parent field',()=>{
    assert.match(check('section','1',null,{area_m2:'100'}),/Measure.*first/);
});
test('unmeasured section may be created under unmeasured parent',()=>{
    assert.equal(check('section','1',null,{}),'');
});
test('sections may not exceed measured usable parent',()=>{
    assert.match(check('section','2',null,{area_m2:'150'}),/exceed.*by 50/);
});
test('editing a section excludes itself from occupied space',()=>{
    assert.equal(check('section','2',21,{name:'Section B2',area_m2:'600'}),'');
});
test('unavailable area needs measurement and description',()=>{
    assert.match(check('field','',null,{name:'Field C',area_m2:'',unavailable_area_m2:'5'}),/Enter a measured area/);
    assert.match(check('field','',null,{name:'Field C',area_m2:'100',unavailable_area_m2:'5'}),/Describe why/);
    assert.equal(check('field','',null,{name:'Field C',area_m2:'100',unavailable_area_m2:'5',unavailable_reason:'Path'}),'');
});
test('nonpositive measured and negative unavailable are rejected',()=>{
    assert.match(check('field','',null,{name:'Field C',area_m2:'0'}),/greater than zero/);
    assert.match(check('field','',null,{name:'Field C',area_m2:'10',unavailable_area_m2:'-1'}),/zero or greater/);
});

test('field available area subtracts unavailable area, not the section count',()=>{
    assert.equal(usableMeasuredArea({area_m2:9500,unavailable_area_m2:9500}),0);
    assert.equal(usableMeasuredArea({area_m2:9500,unavailable_area_m2:0}),9500);
    assert.equal(usableMeasuredArea({area_m2:null,unavailable_area_m2:0}),null);
});
test('fully unavailable parent has a specific actionable validation message',()=>{
    const blockedLand={fields:[{id:1,name:'Field A — Coconut Plantation',area_m2:9500,unavailable_area_m2:9500,sections:[{id:10,name:'Section A1',area_m2:null,unavailable_area_m2:0}]}]};
    assert.match(validateLandEditor({land:blockedLand,type:'section',parentId:1,editingId:10,
        form:{...emptyLandEditor,name:'Section A1',area_m2:'9500'}}),/9500|9,500/);
    assert.match(validateLandEditor({land:blockedLand,type:'section',parentId:1,editingId:10,
        form:{...emptyLandEditor,name:'Section A1',area_m2:'9500'}}),/Edit the parent field/);
});
