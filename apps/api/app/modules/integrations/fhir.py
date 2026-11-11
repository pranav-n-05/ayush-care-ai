"""FHIR R4 mapping (export only). This mapping has NOT been validated against the FHIR
validator or the ABDM implementation guide; it is a starting point for sandbox evaluation."""

from typing import Any

from app.modules.patients.models import Patient

_GENDER = {"female": "female", "male": "male", "intersex": "other", "unknown": "unknown"}


def patient_to_fhir(p: Patient) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": str(p.id),
        "meta": {
            "tag": [
                {
                    "system": "urn:ayushcare:tags",
                    "code": "synthetic-demo",
                    "display": "Unvalidated mapping",
                }
            ]
        },
        "identifier": [{"system": "urn:ayushcare:record-number", "value": p.record_number}],
        "active": p.is_active,
        "name": [{"use": "official", "family": p.family_name or None, "given": [p.given_name]}],
        "gender": _GENDER[p.sex_for_clinical_use],
        "communication": [
            {
                "language": {
                    "coding": [{"system": "urn:ietf:bcp:47", "code": p.preferred_language}]
                },
                "preferred": True,
            }
        ],
    }
    if p.birth_date and p.birth_date_precision == "exact":
        resource["birthDate"] = p.birth_date.isoformat()
    elif p.birth_date and p.birth_date_precision == "year":
        resource["birthDate"] = str(p.birth_date.year)
    telecom = []
    if p.phone:
        telecom.append({"system": "phone", "value": p.phone})
    if p.email:
        telecom.append({"system": "email", "value": p.email})
    if telecom:
        resource["telecom"] = telecom
    if p.city or p.state or p.postal_code or p.address_line:
        resource["address"] = [
            {
                "line": [p.address_line] if p.address_line else None,
                "city": p.city,
                "state": p.state,
                "postalCode": p.postal_code,
                "country": "IN",
            }
        ]
    cleaned: dict[str, Any] = _strip(resource)
    return cleaned


def _strip(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if v is not None and v != [] and v != {}}
    if isinstance(obj, list):
        return [_strip(v) for v in obj if v is not None]
    return obj
