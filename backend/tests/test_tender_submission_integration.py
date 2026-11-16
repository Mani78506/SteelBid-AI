"""Bounded steelbid_test endpoint checks for persisted tender submissions."""
from sqlalchemy import delete, select
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.models.projects import Tender, TenderSubmission, TenderWorkflow
from app.models.fabrication import BOMVersion
from app.models.ops import Approval
from app.models.projects import TenderDocument
from app.models.sales import Quotation
from app.models.ops import AuditEvent
from tests.conftest import login, unique
from tests.test_tender_commercial_approval_and_final_quotation import _ready_estimate

def _finalized_submission_prerequisites(apex_client, client, db):
    tender_id, estimate_id, _ = _ready_estimate(apex_client, db)
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review",json={}).status_code==200
    login(client,"finance@apex.demo"); assert client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve",json={}).status_code==200
    customer=apex_client.get('/api/v1/customers?page_size=1').json()['items'][0]
    assert apex_client.patch(f"/api/v1/tenders/{tender_id}",json={'customer':customer['name']}).status_code==200
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/customer",json={'customer_id':customer['id']}).status_code==200
    quote=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/final-quotation",json={}).json()
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/final-quotation/{quote['id']}/finalize",json={}).status_code==200
    return tender_id, quote['id'], estimate_id


def _confirmed_submission(apex_client, client, db):
    """Create the real finalized-quote -> confirmed-submission chain for outcome tests."""
    tender_id, quote_id, _ = _finalized_submission_prerequisites(apex_client, client, db)
    ready = apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    assert ready["status"] == "READY_FOR_SUBMISSION"
    tender = db.get(Tender, tender_id)
    evidence = TenderDocument(
        organization_id=tender.organization_id, tender_id=tender.id,
        file_name="outcome-ack.pdf", storage_key=f"tests/outcome-{tender.id}.pdf",
        mime_type="application/pdf", size_bytes=4, status="UPLOADED",
    )
    db.add(evidence)
    db.commit()
    created = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions",
        json={
            "quotation_id": quote_id,
            "quotation_version_id": ready["quotation_version_id"],
            "submission_method": "PORTAL",
            "portal_reference": "OUTCOME-ACK-1",
            "evidence_document_id": str(evidence.id),
        },
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]
    confirmed = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    return tender_id, submission_id, quote_id, evidence.id


def test_submission_readiness_requires_finalized_quotation(apex_client):
    tender=apex_client.post('/api/v1/tenders',json={'number':unique('SUB'),'title':'Submission readiness','project_type':'FABRICATION'}).json()
    response=apex_client.get(f"/api/v1/tenders/{tender['id']}/workflow/submission-readiness")
    assert response.status_code==200
    data=response.json(); assert data['status']=='NOT_READY'
    assert any(x['code']=='FINALIZED_QUOTATION_REQUIRED' for x in data['blockers'])


def test_submission_draft_tenant_scope_and_quotation_validation(apex_client, metro_client):
    tender=apex_client.post('/api/v1/tenders',json={'number':unique('SUB'),'title':'Submission draft','project_type':'FABRICATION'}).json()
    response=apex_client.post(f"/api/v1/tenders/{tender['id']}/workflow/submissions",json={'quotation_id':'00000000-0000-0000-0000-000000000000','quotation_version_id':'00000000-0000-0000-0000-000000000000'})
    assert response.status_code==404
    assert metro_client.get(f"/api/v1/tenders/{tender['id']}/workflow/submissions").status_code==404


def test_finalized_quote_to_confirmed_submission_and_correction(apex_client, client, db):
    tender_id, estimate_id, _ = _ready_estimate(apex_client, db)
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review",json={}).status_code==200
    login(client, "finance@apex.demo")
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve",json={}).status_code==200
    customer=apex_client.get('/api/v1/customers?page_size=1').json()['items'][0]
    assert apex_client.patch(f"/api/v1/tenders/{tender_id}",json={'customer':customer['name']}).status_code==200
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/customer",json={'customer_id':customer['id']}).status_code==200
    draft_quote=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/final-quotation",json={}); assert draft_quote.status_code==201, draft_quote.text
    quote_id=draft_quote.json()['id']
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/final-quotation/{quote_id}/finalize",json={}).status_code==200
    ready=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json(); assert ready['status']=='READY_FOR_SUBMISSION'
    tender=db.get(Tender,tender_id); doc=TenderDocument(organization_id=tender.organization_id,tender_id=tender.id,file_name='ack.pdf',storage_key='tests/ack.pdf',mime_type='application/pdf',size_bytes=4,status='UPLOADED')
    db.add(doc); db.commit()
    created=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id'],'submission_method':'PORTAL','portal_reference':'ACK-1','evidence_document_id':str(doc.id)})
    assert created.status_code==201, created.text
    sid=created.json()['id']
    detail=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}").json(); assert detail['status']=='DRAFT'
    confirmed=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}/confirm",json={}); assert confirmed.status_code==200, confirmed.text
    row=db.get(TenderSubmission,sid); db.refresh(row); assert row.status=='CONFIRMED' and row.confirmed_at and row.submitted_by
    db.refresh(tender); assert tender.status=='BID_SUBMITTED'
    workflow=db.scalar(select(TenderWorkflow).where(TenderWorkflow.tender_id==tender.id)); assert workflow.submission_status=='MANUALLY_SUBMITTED'
    assert apex_client.patch(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id']}).status_code==409
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}/confirm",json={}).status_code==409
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}/correction",json={'reason':''}).status_code==422
    correction=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}/correction",json={'reason':'Correct acknowledgement'}); assert correction.status_code==201, correction.text
    child=db.get(TenderSubmission,correction.json()['id']); assert child.parent_submission_id==row.id and child.status=='DRAFT'
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id==row.id,AuditEvent.action=='tender.submission.confirm'))


def test_submission_readiness_requires_finalized_quotation_regression(apex_client):
    tender=apex_client.post('/api/v1/tenders',json={'number':unique('SUB'),'title':'Readiness blockers','project_type':'FABRICATION'}).json()
    result=apex_client.get(f"/api/v1/tenders/{tender['id']}/workflow/submission-readiness").json()
    codes={x['code'] for x in result['blockers']}
    assert result['status']=='NOT_READY' and 'FINALIZED_QUOTATION_REQUIRED' in codes

def test_submission_readiness_customer_and_deadline_blockers(apex_client, client, db):
    tender_id, _, _ = _finalized_submission_prerequisites(apex_client, client, db)
    assert apex_client.patch(f"/api/v1/tenders/{tender_id}",json={'customer':None}).status_code==200
    result=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    assert 'TENDER_CUSTOMER_REQUIRED' in {x['code'] for x in result['blockers']}
    assert apex_client.patch(f"/api/v1/tenders/{tender_id}",json={'customer':'Restored','submission_deadline':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}).status_code==200
    result=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    assert 'SUBMISSION_DEADLINE_PASSED' in {x['code'] for x in result['blockers']}


def test_submission_readiness_requires_persisted_commercial_approval(apex_client, client, db):
    tender_id, _, estimate_id = _finalized_submission_prerequisites(apex_client, client, db)
    db.execute(delete(Approval).where(
        Approval.entity_type == "authoritative_estimate", Approval.entity_id == estimate_id,
    ))
    db.commit()
    result = apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    assert result["status"] == "NOT_READY"
    assert "COMMERCIAL_APPROVAL_REQUIRED" in {x["code"] for x in result["blockers"]}


def test_submission_readiness_rejects_stale_bom_source(apex_client, client, db):
    tender_id, _, _ = _finalized_submission_prerequisites(apex_client, client, db)
    workflow = db.scalar(select(TenderWorkflow).where(TenderWorkflow.tender_id == tender_id))
    current = db.get(BOMVersion, workflow.bom_version_id)
    replacement = BOMVersion(
        organization_id=workflow.organization_id, tender_id=tender_id, bom_code=current.bom_code,
        product_name=current.product_name, version_no=current.version_no + 1, status="APPROVED",
        requirement_snapshot_version=current.requirement_snapshot_version,
    )
    db.add(replacement)
    db.flush()
    workflow.bom_version_id = replacement.id
    db.commit()
    result = apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    assert result["status"] == "NOT_READY"
    assert "REVALIDATION_REQUIRED" in {x["code"] for x in result["blockers"]}

def test_submission_draft_patch_and_evidence_ownership(apex_client, client, db):
    tender_id, quote_id, _ = _finalized_submission_prerequisites(apex_client, client, db)
    ready=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    tender=db.get(Tender,tender_id); same=TenderDocument(organization_id=tender.organization_id,tender_id=tender.id,file_name='same.pdf',storage_key='tests/same.pdf',mime_type='application/pdf',status='UPLOADED')
    other_tender=apex_client.post('/api/v1/tenders',json={'number':unique('OTHER'),'title':'Other evidence','project_type':'FABRICATION'}).json()
    foreign=TenderDocument(organization_id=tender.organization_id,tender_id=other_tender['id'],file_name='foreign.pdf',storage_key='tests/foreign.pdf',mime_type='application/pdf',status='UPLOADED')
    db.add_all([same,foreign]); db.commit()
    created=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id']}).json(); sid=created['id']
    patched=apex_client.patch(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id'],'submission_method':'PORTAL','portal_reference':'P-2','acknowledgment_reference':'A-2','evidence_document_id':str(same.id)})
    assert patched.status_code==200,patched.text
    detail=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}").json()
    assert detail['status']=='DRAFT' and detail['method']=='PORTAL' and detail['portal_reference']=='P-2' and detail['acknowledgment_reference']=='A-2' and detail['evidence_document_id']==str(same.id)
    rejected=apex_client.patch(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id'],'evidence_document_id':str(foreign.id)})
    assert rejected.status_code==400 and rejected.json()['error']['code']=='INVALID_SUBMISSION_EVIDENCE'
    assert apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}").json()['evidence_document_id']==str(same.id)
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}/confirm",json={}).status_code==200
    immutable=apex_client.patch(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id'],'submission_method':'EMAIL'})
    assert immutable.status_code==409

def test_submission_rejects_cross_tenant_evidence(apex_client, metro_client, client, db):
    tender_id, quote_id, _ = _finalized_submission_prerequisites(apex_client, client, db)
    ready=apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/submission-readiness").json()
    foreign_tender=metro_client.post('/api/v1/tenders',json={'number':unique('METRO'),'title':'Foreign evidence','project_type':'FABRICATION'}).json()
    foreign_row=db.get(Tender,foreign_tender['id'])
    foreign_doc=TenderDocument(organization_id=foreign_row.organization_id,tender_id=foreign_row.id,file_name='foreign.pdf',storage_key='tests/foreign-cross.pdf',mime_type='application/pdf',status='UPLOADED')
    db.add(foreign_doc);db.commit()
    sid=apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submissions",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id']}).json()['id']
    response=apex_client.patch(f"/api/v1/tenders/{tender_id}/workflow/submissions/{sid}",json={'quotation_id':quote_id,'quotation_version_id':ready['quotation_version_id'],'evidence_document_id':str(foreign_doc.id)})
    assert response.status_code==400 and response.json()['error']['code']=='INVALID_SUBMISSION_EVIDENCE'
    assert str(foreign_doc.id) not in response.text


def test_confirmed_submission_records_won_outcome_and_audit(apex_client, client, db):
    tender_id, submission_id, quote_id, evidence_id = _confirmed_submission(apex_client, client, db)
    original = db.get(TenderSubmission, submission_id)
    response = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "WON", "outcome_date": "2026-11-06", "reference": "AWARD-42", "remarks": "Award letter received", "award_value": "123456.7800", "currency": "INR"},
    )
    assert response.status_code == 200, response.text
    db.refresh(original)
    tender = db.get(Tender, tender_id)
    assert tender.status == "WON"
    assert original.outcome_status == "WON"
    assert original.outcome_date.isoformat() == "2026-11-06"
    assert original.outcome_reference == "AWARD-42"
    assert original.outcome_remarks == "Award letter received"
    assert original.outcome_value == Decimal("123456.7800")
    assert original.outcome_currency == "INR"
    assert str(original.quotation_id) == quote_id and original.evidence_document_id == evidence_id
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == original.id, AuditEvent.action == "tender.submission.outcome"))


def test_confirmed_submission_records_lost_outcome(apex_client, client, db):
    tender_id, submission_id, _, _ = _confirmed_submission(apex_client, client, db)
    response = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "LOST", "outcome_date": "2026-11-06", "reference": "LOSS-7", "remarks": "Commercial ranking"},
    )
    assert response.status_code == 200, response.text
    row = db.get(TenderSubmission, submission_id)
    assert db.get(Tender, tender_id).status == "LOST"
    assert row.outcome_status == "LOST" and row.outcome_date.isoformat() == "2026-11-06"
    assert row.outcome_reference == "LOSS-7" and row.outcome_remarks == "Commercial ranking"
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == row.id, AuditEvent.action == "tender.submission.outcome"))


def test_confirmed_submission_records_cancelled_outcome(apex_client, client, db):
    tender_id, submission_id, _, _ = _confirmed_submission(apex_client, client, db)
    response = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "CANCELLED", "outcome_date": "2026-11-06", "reference": "CANCEL-9", "remarks": "Issuer cancelled tender"},
    )
    assert response.status_code == 200, response.text
    row = db.get(TenderSubmission, submission_id)
    assert db.get(Tender, tender_id).status == "CANCELLED"
    assert row.outcome_status == "CANCELLED" and row.outcome_reference == "CANCEL-9"
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == row.id, AuditEvent.action == "tender.submission.outcome"))


def test_outcome_rejects_invalid_state_cross_tenant_and_conflict(apex_client, metro_client, client, db):
    tender_id, submission_id, quote_id, evidence_id = _confirmed_submission(apex_client, client, db)
    invalid = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "INVALID", "outcome_date": "2026-11-06"},
    )
    assert invalid.status_code == 422
    cross_tenant = metro_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "WON", "outcome_date": "2026-11-06"},
    )
    # The outcome handler deliberately returns the same prerequisite error for
    # a foreign submission as for an unconfirmed local one, avoiding existence
    # disclosure across tenants.
    assert cross_tenant.status_code == 400
    assert cross_tenant.json()["error"]["code"] == "CONFIRMED_SUBMISSION_REQUIRED"
    assert apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "WON", "outcome_date": "2026-11-06"},
    ).status_code == 200
    conflict_response = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
        json={"status": "LOST", "outcome_date": "2026-11-07"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "OUTCOME_ALREADY_RECORDED"
    row = db.get(TenderSubmission, submission_id)
    assert row.outcome_status == "WON" and str(row.quotation_id) == quote_id and row.evidence_document_id == evidence_id
    draft = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions",
        json={"quotation_id": quote_id, "quotation_version_id": str(row.quotation_version_id)},
    ).json()
    not_confirmed = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{draft['id']}/outcome",
        json={"status": "WON", "outcome_date": "2026-11-06"},
    )
    assert not_confirmed.status_code == 400
    assert not_confirmed.json()["error"]["code"] == "CONFIRMED_SUBMISSION_REQUIRED"


def test_submission_summary_counts_readiness_deadlines_and_corrections(apex_client, client, db):
    baseline = apex_client.get("/api/v1/dashboard/submission-summary").json()
    upcoming_tender, _, _ = _finalized_submission_prerequisites(apex_client, client, db)
    outside_tender, _, _ = _finalized_submission_prerequisites(apex_client, client, db)
    now = datetime.now(timezone.utc)
    assert apex_client.patch(f"/api/v1/tenders/{upcoming_tender}", json={"submission_deadline": (now + timedelta(days=3)).isoformat()}).status_code == 200
    assert apex_client.patch(f"/api/v1/tenders/{outside_tender}", json={"submission_deadline": (now + timedelta(days=8)).isoformat()}).status_code == 200
    ready_summary = apex_client.get("/api/v1/dashboard/submission-summary").json()
    assert ready_summary["ready_for_submission"] == baseline["ready_for_submission"] + 2
    assert ready_summary["upcoming_deadlines"] == baseline["upcoming_deadlines"] + 1

    tender_id, submission_id, _, _ = _confirmed_submission(apex_client, client, db)
    correction = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/correction",
        json={"reason": "Correct portal acknowledgement"},
    )
    assert correction.status_code == 201, correction.text
    assert apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{correction.json()['id']}/confirm", json={}
    ).status_code == 200
    summary = apex_client.get("/api/v1/dashboard/submission-summary").json()
    assert summary["confirmed_submissions"] == baseline["confirmed_submissions"] + 1
    assert summary["ready_for_submission"] == ready_summary["ready_for_submission"]
    assert summary["upcoming_deadlines"] == ready_summary["upcoming_deadlines"]
    assert summary["attention"] == baseline["attention"]

    # A second historical confirmed revision still represents one submitted
    # tender.  The third, still-draft correction is one attention item.
    second = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/correction",
        json={"reason": "Correct acknowledgement again"},
    )
    assert second.status_code == 201, second.text
    assert apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{second.json()['id']}/confirm", json={}
    ).status_code == 200
    deduped = apex_client.get("/api/v1/dashboard/submission-summary").json()
    assert deduped["confirmed_submissions"] == summary["confirmed_submissions"]
    assert deduped["attention"] == summary["attention"]
    third = apex_client.post(
        f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/correction",
        json={"reason": "Awaiting final correction"},
    )
    assert third.status_code == 201, third.text
    attention = apex_client.get("/api/v1/dashboard/submission-summary").json()
    assert attention["confirmed_submissions"] == summary["confirmed_submissions"]
    assert attention["attention"] == baseline["attention"] + 1


def test_submission_summary_counts_outcomes_and_isolates_tenants(apex_client, metro_client, client, db):
    apex_before = apex_client.get("/api/v1/dashboard/submission-summary").json()
    metro_before = metro_client.get("/api/v1/dashboard/submission-summary").json()
    for status in ("WON", "LOST", "CANCELLED"):
        tender_id, submission_id, _, _ = _confirmed_submission(apex_client, client, db)
        result = apex_client.post(
            f"/api/v1/tenders/{tender_id}/workflow/submissions/{submission_id}/outcome",
            json={"status": status, "outcome_date": "2026-11-06", "reference": f"{status}-SUMMARY"},
        )
        assert result.status_code == 200, result.text

    # Persist foreign tenant state directly in the isolated fixture database;
    # it must affect only Metro's aggregate, never Apex's response.
    foreign = metro_client.post("/api/v1/tenders", json={"number": unique("METRIC"), "title": "Metro outcome", "project_type": "FABRICATION"}).json()
    foreign_tender = db.get(Tender, foreign["id"])
    foreign_tender.status = "WON"
    db.commit()

    apex_after = apex_client.get("/api/v1/dashboard/submission-summary").json()
    metro_after = metro_client.get("/api/v1/dashboard/submission-summary").json()
    assert apex_after["confirmed_submissions"] == apex_before["confirmed_submissions"] + 3
    assert apex_after["won"] == apex_before["won"] + 1
    assert apex_after["lost"] == apex_before["lost"] + 1
    # CANCELLED is not a WON/LOST outcome metric.
    assert apex_after["won"] + apex_after["lost"] == apex_before["won"] + apex_before["lost"] + 2
    assert metro_after["won"] == metro_before["won"] + 1
    assert apex_after["won"] == apex_before["won"] + 1
