"""Versioned variety references; estimates never become physical readiness.

References are planning guidance, not a recorded crop observation. Anchors
must refer to the appropriate biological event (shooting vs planting).
Missing or unverified anchors yield no invented harvest date.
"""
from __future__ import annotations
from datetime import date, timedelta
import re
from sqlalchemy import select
from app.models.crop import Crop, CropYieldRecord
from app.models.crop_maturity import CropMaturityEvent
from app.core.farm_time import farm_today

VERSION = 1
def key(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').casefold())

# Time ranges and event anchors are crop/variety-specific. Profiles with
# insufficient variety evidence deliberately have no numerical range.
PROFILES = {
    ('banana','lakatan'): ('shooting',84,98,None,'verified','Philippine DA Banana Production Manual: 12–14 weeks after shooting','bunch_and_pseudostem'),
    ('banana','latundan'): ('shooting',63,77,None,'verified','Philippine DA Banana Production Manual: 9–11 weeks after shooting','bunch_and_pseudostem'),
    ('banana','saba'): ('shooting',140,168,None,'verified','Philippine DA Banana Production Manual: 20–24 weeks after shooting','bunch_and_pseudostem'),
    ('coconut','tall'): ('flowering',330,365,(45,60),'crop_reference','Philippine coconut copra standard: mature fruit 11–12 months from flowering; harvest at least every 45 days','repeated_fruit'),
    ('coconut','dwarf'): ('flowering',330,365,(45,60),'crop_reference','Philippine coconut copra standard: mature fruit 11–12 months from flowering; harvest at least every 45 days','repeated_fruit'),
    ('cassava','lakan1'): ('planting',None,None,None,'inspection_required','PhilRootcrops: variety-specific maturity requires confirmation by root sampling','root_harvest'),
    ('sweetpotato','sp20'): ('planting',105,120,None,'reference_range','PhilRootcrops PSB Sp20 production guide: 105–120 days','storage_root'),
    ('sweetpotato','sp30'): ('planting',105,120,None,'reference_range','Visayas State University annual report: NSIC Sp30 105–120 days','storage_root'),
    ('taro','iniito'): ('planting',None,None,None,'inspection_required','DA Bicol taro growing guidance; locally verify Iniito/VG2 maturity','corm_harvest'),
    ('taro','morondon'): ('planting',None,None,None,'inspection_required','DA Bicol taro growing guidance; locally verify Morondon maturity','corm_harvest'),
    ('basil','genovese'): ('planting',None,None,(21,35),'inspection_required','University extension basil repeated-cutting guidance; timing varies by regrowth','repeated_cutting'),
    ('basil','siamqueen'): ('planting',None,None,(21,35),'inspection_required','University extension basil repeated-cutting guidance; timing varies by regrowth','repeated_cutting'),
}
SOURCE_LINKS = {
    'banana': 'https://hvcdp.da.gov.ph/wp-content/uploads/2022/05/Banana-Production-Manual.pdf',
    'coconut': 'https://www.pca.gov.ph/images/Article/market_2025/PNS-BAFPS_44-2009_-_Prevention_and_Reduction_of_Aflatoxin_Contamination_in_Copra__Code_of_Practice_1.pdf',
    'sweetpotato': 'https://philrootcrops.vsu.edu.ph/',
    'taro': 'https://hvcdp.da.gov.ph/production-manuals/',
    'basil': 'https://extension.umn.edu/',
    'cassava': 'https://philrootcrops.vsu.edu.ph/',
}
def normalized(name,variety):
    crop=key(name); variety=key(variety)
    if crop in {'kamote','sweetpotatoes'}:crop='sweetpotato'
    if crop=='gabi':crop='taro'
    if crop=='sweetpotato' and variety in {'psbsp20','nsicsp20'}:variety='sp20'
    if crop=='sweetpotato' and variety=='nsicsp30':variety='sp30'
    if crop=='taro' and variety in {'vg2','iniitovg2'}:variety='iniito'
    if crop=='basil' and variety=='queen':variety='siamqueen'
    return crop,variety

def profile_for(name,variety):
    crop, cultivar=normalized(name,variety)
    row=PROFILES.get((crop,cultivar))
    if row is None:
        return dict(version=VERSION, crop=name, variety=variety, anchor_kind=None,
            min_days=None,max_days=None,repeat_days=None,confidence='unverified',
            source='No validated reference yet for this combination', source_url=None,
            harvest_behavior='inspect_before_harvest')
    event,minimum,maximum,repeat,confidence,source,behavior=row
    return dict(version=VERSION,crop=name,variety=variety,anchor_kind=event,
        min_days=minimum,max_days=maximum,repeat_days=repeat,confidence=confidence,
        source=source,source_url=SOURCE_LINKS.get(crop),harvest_behavior=behavior)

def prediction(profile, anchor):
    if anchor is None or profile['min_days'] is None or profile['max_days'] is None:
        return None, None
    return anchor+timedelta(days=profile['min_days']),anchor+timedelta(days=profile['max_days'])

def readiness_state(crop, first, last, today=None):
    today=today or farm_today()
    if crop.status in {'Harvested','Failed'}:return 'completed'
    if crop.confirmed_ready_at and crop.status in {'Ready for Harvest','Harvesting'}:return 'confirmed_ready'
    if crop.status=='Harvesting':return 'harvesting'
    if first is None:return 'not_estimated'
    if today<first-timedelta(days=7):return 'growing'
    if today<first:return 'approaching_harvest'
    return 'inspection_required'  # date alone never proves physical readiness

def planning_snapshot(db,crop,today=None):
    today=today or farm_today()
    profile=profile_for(crop.name,crop.variety)
    event_kind=profile['anchor_kind']
    event = db.scalar(select(CropMaturityEvent).where(
        CropMaturityEvent.crop_id == crop.id, CropMaturityEvent.event_kind==event_kind
    ).order_by(CropMaturityEvent.observed_date.desc(),CropMaturityEvent.id.desc()).limit(1)) if event_kind not in {None,'planting'} else None
    anchor=crop.planting_date if event_kind=='planting' and crop.planting_date_precision!='unknown' else (event.observed_date if event else None)
    first,last=prediction(profile,anchor)
    last_yield=db.scalar(select(CropYieldRecord).where(
        CropYieldRecord.crop_id==crop.id
    ).order_by(CropYieldRecord.harvest_date.desc(), CropYieldRecord.id.desc()).limit(1))
    next_first=next_last=None
    if (last_yield is not None and profile['repeat_days'] is not None
        and crop.status not in {'Harvested','Failed'}):
        low,high=profile['repeat_days']
        next_first=last_yield.harvest_date+timedelta(days=low)
        next_last=last_yield.harvest_date+timedelta(days=high)
    if crop.status in {'Harvested', 'Failed'}:
        phase = 'Cycle completed'
    elif crop.status == 'Harvesting':
        phase = 'Harvesting / Production'
    elif crop.confirmed_ready_at and crop.status == 'Ready for Harvest':
        phase = 'Ready for Harvest (inspected)'
    elif last_yield is not None and profile['repeat_days'] is not None:
        phase = 'Next harvest cycle'
    elif (event is not None and crop.last_observation_date is not None
          and crop.last_observation_date > event.observed_date and crop.observed_growth_stage):
        phase = crop.observed_growth_stage
    elif event is not None:
        phase = 'Bunch development' if event_kind == 'shooting' else 'Flower / fruit development'
    elif crop.observed_growth_stage:
        phase = crop.observed_growth_stage
    elif crop.planting_date is None:
        phase = 'Not estimated'
    elif crop.planting_date >= today:
        phase = 'New planting / Establishment'
    else:
        phase = 'Growing / Vegetative'
    return dict(
        crop_id=crop.id,crop_code=crop.crop_code,field=crop.field,
        **profile, anchor_date=anchor, last_event_id=event.id if event else None,
        earliest_harvest=first,latest_harvest=last,
        recorded_expected_harvest=crop.estimated_harvest,
        readiness_state=(
            ('growing' if today < next_first-timedelta(days=7) else
             'approaching_harvest' if today < next_first else 'inspection_required')
            if next_first is not None and crop.status == 'Harvesting'
            and not crop.confirmed_ready_at
            else readiness_state(crop,first,last,today)
        ), growth_phase=phase,
        next_cycle_earliest=next_first,next_cycle_latest=next_last,
        next_cycle_is_suggestion=True,
        explanation='Estimates guide planning; an authorized physical inspection confirms actual readiness.',
    )
