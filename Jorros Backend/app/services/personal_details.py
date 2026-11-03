from app.schemas.personal_details import PersonalDetails

def apply_personal_details(record, changes):
    supplied = changes.get('personal_details')
    if supplied is not None:
        details = PersonalDetails.model_validate(supplied)
        previous = record.personal_details or {}
        record.personal_details = details.model_dump()
        if details.full_name:
            record.full_name = details.full_name
        if hasattr(record, 'address') and (details.address is not None or previous.get('address')):
            record.address = details.address.formatted if details.address else None
    elif 'full_name' in changes and record.personal_details and changes['full_name'] != record.full_name:
        details = dict(record.personal_details)
        details.update({key: None for key in ('first_name', 'middle_name', 'surname', 'suffix')})
        record.personal_details = details
