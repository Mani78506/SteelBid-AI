import * as React from "react";
import { Badge, Button, Input, Modal, Select } from "@/components/ui";

type OutcomeStatus = "WON" | "LOST" | "CANCELLED";
export interface SubmissionReadiness { status: string; blockers?: { code: string; message?: string }[] }
export interface TenderEvidenceDocument { id: string; file_name: string }
export interface TenderSubmission { id: string; status: string; method?: string | null; portal_reference?: string | null; acknowledgment_reference?: string | null; evidence_document_id?: string | null; submitted_at?: string | null; confirmed_at?: string | null }
export interface SubmissionForm { method: string; portal_reference: string; acknowledgment_reference: string; evidence_document_id: string; submitted_at: string }
export interface OutcomeForm { status: OutcomeStatus; outcome_date: string; reference: string; remarks: string; award_value: string; currency: string }
type MutationControl<T = void> = { isPending: boolean; isSuccess?: boolean; mutate: (argument: T) => void };

interface Props {
  readiness?: SubmissionReadiness; submissions: TenderSubmission[]; documents: TenderEvidenceDocument[]; deadline?: string | null;
  form: SubmissionForm; setForm: React.Dispatch<React.SetStateAction<SubmissionForm>>;
  correctionReason: string; setCorrectionReason: React.Dispatch<React.SetStateAction<string>>;
  outcome: OutcomeForm; setOutcome: React.Dispatch<React.SetStateAction<OutcomeForm>>;
  prepare: MutationControl; saveDraft: MutationControl<string>; confirm: MutationControl<string>; correction: MutationControl<string>; recordOutcome: MutationControl<string>;
}

export function TenderSubmissionPanel({ readiness, submissions, documents, deadline, form, setForm, correctionReason, setCorrectionReason, outcome, setOutcome, prepare, saveDraft, confirm, correction, recordOutcome }: Props) {
  const [confirmId, setConfirmId] = React.useState<string | null>(null);
  const [outcomeId, setOutcomeId] = React.useState<string | null>(null);
  const blockers = readiness?.blockers ?? [];
  const pending = prepare.isPending || saveDraft.isPending || confirm.isPending || correction.isPending || recordOutcome.isPending;
  const selected = submissions.find((item) => item.id === confirmId);
  const selectedOutcome = submissions.find((item) => item.id === outcomeId);
  const canConfirm = (item: TenderSubmission) => item.status === "DRAFT" && readiness?.status === "READY_FOR_SUBMISSION" && Boolean(item.method && item.portal_reference && item.evidence_document_id);
  React.useEffect(() => {
    if (confirm.isSuccess) setConfirmId(null);
  }, [confirm.isSuccess]);
  React.useEffect(() => {
    if (recordOutcome.isSuccess) setOutcomeId(null);
  }, [recordOutcome.isSuccess]);

  return <section className="mt-4 rounded-xl border border-blue-200 bg-blue-50/30 p-4" aria-label="Tender Submission">
    <div className="flex flex-wrap justify-between gap-2"><div><b>Tender Submission</b><p className="text-xs text-slate-600">Manual evidence recording only. SteelBid does not submit to external portals.</p></div><Badge value={readiness?.status ?? "LOADING"} /></div>
    <p className="mt-2 text-xs">Deadline: <b>{deadline ?? "Not recorded"}</b></p>
    {blockers.length > 0 && <ul className="mt-2 list-disc rounded border border-amber-200 bg-amber-50 p-3 pl-7 text-xs text-amber-900">{blockers.map((blocker) => <li key={blocker.code}>{blocker.code}{blocker.message ? `: ${blocker.message}` : ""}</li>)}</ul>}
    <div className="mt-3 grid gap-2 sm:grid-cols-3">
      <Input aria-label="Submission method" placeholder="Submission method" value={form.method} disabled={pending} onChange={(event) => setForm((value) => ({ ...value, method: event.target.value }))} />
      <Input aria-label="Portal/reference number" placeholder="Portal/reference number" value={form.portal_reference} disabled={pending} onChange={(event) => setForm((value) => ({ ...value, portal_reference: event.target.value }))} />
      <Input aria-label="Acknowledgment reference" placeholder="Acknowledgment reference" value={form.acknowledgment_reference} disabled={pending} onChange={(event) => setForm((value) => ({ ...value, acknowledgment_reference: event.target.value }))} />
      <Select aria-label="Tender evidence" value={form.evidence_document_id} disabled={pending} onChange={(event) => setForm((value) => ({ ...value, evidence_document_id: event.target.value }))}><option value="">Link tender evidence</option>{documents.map((document) => <option value={document.id} key={document.id}>{document.file_name}</option>)}</Select>
      <Input aria-label="Submission timestamp" type="datetime-local" value={form.submitted_at} disabled={pending} onChange={(event) => setForm((value) => ({ ...value, submitted_at: event.target.value }))} />
      <Button size="sm" disabled={readiness?.status !== "READY_FOR_SUBMISSION" || pending} loading={prepare.isPending} onClick={() => prepare.mutate(undefined)}>Prepare Submission</Button>
    </div>
    <div className="mt-3 space-y-2">{submissions.length === 0 ? <p className="text-xs text-slate-500">No submission record exists.</p> : submissions.map((item) => <div key={item.id} className="rounded border bg-white p-3 text-xs">
      <div className="flex justify-between"><b>{item.status}</b><span>{item.confirmed_at ?? "Draft"}</span></div><p>{item.method ?? "Method missing"} · {item.portal_reference ?? "Reference missing"}</p>
      {item.status === "DRAFT" ? <div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={pending} loading={saveDraft.isPending} onClick={() => saveDraft.mutate(item.id)}>Save Draft</Button><Button size="sm" disabled={!canConfirm(item) || pending} loading={confirm.isPending} onClick={() => setConfirmId(item.id)}>Confirm Submission</Button></div> :
      <div className="mt-2 grid gap-2 sm:grid-cols-3"><Input placeholder="Correction reason" value={correctionReason} disabled={pending} onChange={(event) => setCorrectionReason(event.target.value)} /><Button size="sm" disabled={!correctionReason.trim() || pending} loading={correction.isPending} onClick={() => correction.mutate(item.id)}>Create Correction</Button><Select aria-label="Tender outcome" value={outcome.status} disabled={pending} onChange={(event) => setOutcome((value) => ({ ...value, status: event.target.value as OutcomeStatus }))}><option value="WON">WON</option><option value="LOST">LOST</option><option value="CANCELLED">CANCELLED</option></Select><Input aria-label="Outcome date" type="date" value={outcome.outcome_date} disabled={pending} onChange={(event) => setOutcome((value) => ({ ...value, outcome_date: event.target.value }))} /><Input aria-label="Outcome reference" placeholder="Decision reference" value={outcome.reference} disabled={pending} onChange={(event) => setOutcome((value) => ({ ...value, reference: event.target.value }))} /><Input aria-label="Outcome remarks" placeholder="Outcome remarks" value={outcome.remarks} disabled={pending} onChange={(event) => setOutcome((value) => ({ ...value, remarks: event.target.value }))} /><Input aria-label="Award value" type="number" min="0" placeholder="Award value" value={outcome.award_value} disabled={pending} onChange={(event) => setOutcome((value) => ({ ...value, award_value: event.target.value }))} /><Input aria-label="Award currency" placeholder="Currency" value={outcome.currency} disabled={pending} onChange={(event) => setOutcome((value) => ({ ...value, currency: event.target.value }))} /><Button size="sm" disabled={!outcome.outcome_date || pending} loading={recordOutcome.isPending} onClick={() => setOutcomeId(item.id)}>Record Outcome</Button></div>}
    </div>)}</div>
    <Modal open={Boolean(confirmId)} onClose={() => !confirm.isPending && setConfirmId(null)} title="Confirm manual submission"><div className="space-y-3"><p className="text-sm text-slate-700">Confirm this was completed outside SteelBid. This records supplied evidence only; it does not submit to an external portal.</p><p className="rounded bg-slate-50 p-2 text-xs">Method: <b>{selected?.method}</b> · Reference: <b>{selected?.portal_reference}</b></p><div className="flex justify-end gap-2"><Button variant="outline" disabled={confirm.isPending} onClick={() => setConfirmId(null)}>Cancel</Button><Button loading={confirm.isPending} onClick={() => confirmId && confirm.mutate(confirmId)}>Confirm Submission</Button></div></div></Modal>
    <Modal open={Boolean(outcomeId)} onClose={() => !recordOutcome.isPending && setOutcomeId(null)} title="Confirm tender outcome"><div className="space-y-3"><p className="text-sm text-slate-700">Record an outcome from a confirmed external decision. This does not infer an award or submit anything externally.</p><p className="rounded bg-slate-50 p-2 text-xs">Outcome: <b>{outcome.status}</b> · Date: <b>{outcome.outcome_date}</b></p><p className="text-xs text-slate-500">Submission: {selectedOutcome?.portal_reference ?? "reference not recorded"}</p><div className="flex justify-end gap-2"><Button variant="outline" disabled={recordOutcome.isPending} onClick={() => setOutcomeId(null)}>Cancel</Button><Button loading={recordOutcome.isPending} onClick={() => outcomeId && recordOutcome.mutate(outcomeId)}>Record Outcome</Button></div></div></Modal>
  </section>;
}
