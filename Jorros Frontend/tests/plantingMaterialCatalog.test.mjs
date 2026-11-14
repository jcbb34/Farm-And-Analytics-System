import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogCrops, catalogVarieties, plantingMethod, plantingMethods } from '../src/services/plantingMaterialCatalog.js';

const known = [
    { crop_key:'banana', crop_name:'Banana', variety_key:'lakatan', variety_name:'Lakatan',
        material_types:[{ kind:'sucker', category:'Planting Material', unit:'suckers', default_units_per_position:1 },
            { kind:'plantlet', category:'Planting Material', unit:'pieces', default_units_per_position:1 }] },
    { crop_key:'banana', crop_name:'Banana', variety_key:'saba', variety_name:'Saba',
        material_types:[{ kind:'sucker', category:'Planting Material', unit:'suckers', default_units_per_position:1 }] },
    { crop_key:'basil', crop_name:'Basil', variety_key:'genovese', variety_name:'Genovese',
        material_types:[{ kind:'seedling', category:'Seedlings', unit:'seedlings', default_units_per_position:1 },
            { kind:'seed', category:'Seeds', unit:'seeds', default_units_per_position:null }] },
];

test('inventory chooser contains only known crops and their exact varieties', () => {
    assert.deepEqual(catalogCrops(known), [['banana','Banana'],['basil','Basil']]);
    assert.deepEqual(catalogVarieties(known,'banana'),[['lakatan','Lakatan'],['saba','Saba']]);
    assert.deepEqual(catalogVarieties(known,'unknown'),[]);
});

test('recommended planting materials are variety and category restricted', () => {
    assert.deepEqual(plantingMethods(known,'banana','lakatan','Planting Material').map(x=>x.kind), ['sucker','plantlet']);
    assert.deepEqual(plantingMethods(known,'banana','lakatan','Seeds'), []);
    assert.equal(plantingMethod(known,'banana','lakatan','seed'), null);
    assert.equal(plantingMethod(known,'banana','saba','plantlet'), null);
    assert.equal(plantingMethod(known,'basil','genovese','seed').default_units_per_position, null);
});
