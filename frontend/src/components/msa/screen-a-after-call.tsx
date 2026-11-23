/* eslint-disable prettier/prettier -- compact Wrap Up presentation */
import { useEffect, useState } from "react";
import {
  Bell,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  FileDown,
  FileText,
  MailCheck,
  Printer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { VoiceBookingProof } from "@/lib/voice-booking-proof";
import type { CrmProof } from "@/lib/crm-proof";
import { AfterCallCard } from "./after-call-card";

/**
 * Never synthesize a booking receipt from a spoken utterance. The caller must
 * supply a persisted, scope-validated synthetic booking read-back before
 * a letter can be previewed or printed.
 */
export type ConfirmedSyntheticBooking = {
  synthetic: true;
  verifiedReadback: true;
  veteranName: string;
  careType: string;
  facility: string;
  appointmentDate: string;
  localTimeAndZone: string;
  visitType: string;
  confirmationReference: string;
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => {
    const replacements: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return replacements[c] ?? c;
  });
}

export function printableLetterHtml(booking: ConfirmedSyntheticBooking): string {
  const rows: [string, string][] = [
    ["Appointment Type", booking.careType],
    ["Facility", booking.facility],
    ["Appointment Date", booking.appointmentDate],
    ["Time & Time Zone", booking.localTimeAndZone],
    ["Visit Type", booking.visitType],
    ["Confirmation Reference", booking.confirmationReference],
  ];
  return `<!doctype html><html lang="en"><head><meta charset="utf-8" />
<title>Synthetic Appointment Confirmation Letter</title>
<style>body{font:16px/1.6 Arial,sans-serif;color:#172c4e;margin:40px auto;max-width:720px;padding:0 24px}
header{border-bottom:3px solid #005ea2;padding-bottom:16px}h1{font-size:23px}
td{padding:8px;border-bottom:1px solid #ddd}table{width:100%;border-collapse:collapse;margin:20px 0}
footer{margin-top:36px;padding:16px;border:2px solid #b91c1c;color:#991b1b;font-weight:bold}
@media print{body{margin:20mm auto}}</style></head><body>
<header><strong>Veteran Access Bridge</strong><h1>Synthetic Appointment Confirmation Letter</h1></header>
<p>Dear ${escapeHtml(booking.veteranName)},</p>
<p>This letter confirms the synthetic appointment recorded during your demonstration call with Avery.</p>
<table><tbody>${rows
    .map(
      ([label, value]) =>
        `<tr><td><strong>${escapeHtml(label)}</strong></td><td>${escapeHtml(value)}</td></tr>`,
    )
    .join("")}</tbody></table>
<p>Thank you for using Veteran Access Bridge.</p>
<footer>SANDBOX DOCUMENT · NOT A REAL VA APPOINTMENT<br />
This document is for demonstration purposes only and does not represent an appointment in a VA healthcare system.</footer>

</body></html>`;
}

export function AfterCallWork({
  ended,
  receipt,
  bookingProof = null,
  crmReceipts = [],
  summaryReady = false,
  notificationAcknowledged = false,
  encounterLogged = false,
  afterCall = null,
  retryAfterCall = () => {},
}: {
  ended: boolean;
  receipt: ConfirmedSyntheticBooking | null;
  bookingProof?: VoiceBookingProof | null;
  crmReceipts?: CrmProof[];
  summaryReady?: boolean;
  notificationAcknowledged?: boolean;
  encounterLogged?: boolean;
  afterCall?: import("@/lib/after-call").AfterCall | null;
  retryAfterCall?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (ended) setExpanded(true);
  }, [ended]);
  const ready = [summaryReady, !!receipt, notificationAcknowledged, encounterLogged].filter(
    Boolean,
  ).length;
  const complete = ended && afterCall?.status === "COMPLETE" && afterCall.persisted
    && !!afterCall.record_id && !!afterCall.summary?.trim()
    && (!(bookingProof || receipt) || (
      !!afterCall.letter?.text.trim() && afterCall.letter.delivery_status === "NOT_SENT"
      && bookingProof?.crm_note_status === "SAVED"
    ));
  const openLetter = (print: boolean) => {
    if (!receipt || !receipt.verifiedReadback || !receipt.synthetic) return;
    const win = window.open("", "_blank");
    if (!win) return;
    win.opener = null;
    win.document.open();
    win.document.write(printableLetterHtml(receipt));
    win.document.close();
    win.focus();
    if (print) win.print();
  };
  return (
    <section
      aria-label="Wrap Up"
      data-completion-state={complete ? "complete" : "pending"}
      className={`msa-workspace-after-panel rounded-xl border ${complete ? "border-emerald-600 bg-emerald-50" : "border-[#dfe1e2] bg-white"}`}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        className="flex min-h-12 w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-[#005ea2]"
      >
        <span className="flex flex-wrap items-center gap-2">
          {complete && <CheckCircle2 className="size-5 text-emerald-700" aria-hidden="true" />}
          <strong className={`text-base ${complete ? "text-emerald-900" : "text-[#162e51]"}`}>Wrap Up</strong>
          <span className="text-xs text-slate-500">
            {complete ? "After-call work complete · verified records saved" : ended ? "Call ended · review verified records" : "Available after call completion"}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
          <span role="status" className={complete ? "rounded-full bg-emerald-700 px-2 py-1 font-semibold text-white" : ""}>
            {complete ? "Complete" : afterCall ? "Pending" : `${ready} / 4 ready`}
          </span>{" "}
          <ChevronDown className={`size-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </span>
      </button>
      {expanded && (
        <div className="space-y-3 border-t px-4 py-3">
          {afterCall && <AfterCallCard result={afterCall} retry={retryAfterCall} complete={complete} />}
          <article
            aria-label="CRM save receipts"
            className="rounded-md border bg-slate-50 p-3 text-sm"
          >
            <h3 className="font-semibold text-[#162e51]">CRM · Call records</h3>
            {bookingProof?.crm_note_status === "SAVED" && (
              <div className="mt-2">
                <strong>Automatic booking note saved</strong>
                <p className="break-all text-xs">{bookingProof.crm_note_id}</p>
                <p className="text-xs">
                  Created by the trusted booking service from the verified appointment receipt.
                </p>
              </div>
            )}
            {bookingProof?.crm_note_status === "PENDING" && (
              <p className="mt-2 text-amber-800">
                Automatic booking note pending. Your verified appointment is unchanged.
              </p>
            )}
            {crmReceipts.length === 0 && !bookingProof?.crm_note_status ? (
              <p className="mt-1 text-xs text-slate-600">
                No verified CRM save receipt for this call yet.
              </p>
            ) : (
              <ul className="mt-2 space-y-2">
                {crmReceipts.map((item, index) => (
                  <li key={`${item.record_id}-${item.version}-${index}`}>
                    <strong>
                      {item.operation === "record_crm_interaction"
                        ? "Call note saved"
                        : item.operation === "create_crm_follow_up"
                          ? "Follow-up task saved"
                          : "Follow-up task updated"}
                    </strong>
                    <p className="break-all text-xs">
                      {item.record_id} · Version {item.version}
                      {item.replayed ? " · Existing receipt" : ""}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-xs text-slate-600">
              Synthetic CRM records. A saved task does not confirm human follow-up or an
              appointment.
            </p>
          </article>
          {bookingProof?.state === "BOOKED_SIMULATED" && bookingProof.appointment_id && (
            <article
              aria-label="Verified synthetic booking receipt"
              className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-950"
            >
              <h3 className="font-semibold">Verified synthetic booking receipt</h3>
              <p className="mt-1 break-all">Confirmation: {bookingProof.appointment_id}</p>
              <p>
                Appointment:{" "}
                {new Date(bookingProof.begins_at).toLocaleString("en-US", {
                  timeZone: "America/Chicago",
                  timeZoneName: "short",
                })}
              </p>
              <p className="mt-1 text-xs">
                Read back from the backend for this call. This is not a real VA appointment.
              </p>
            </article>
          )}
          {!afterCall && (
            <>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="inline-flex items-center gap-1 rounded-md border px-2 py-1">
                  <Bell className="size-3.5" /> Notification Status ·{" "}
                  {notificationAcknowledged ? "Receipt verified" : "Pending"}
                </span>
                <span className="inline-flex items-center gap-1 rounded-md border px-2 py-1">
                  <MailCheck className="size-3.5" /> Encounter Log ·{" "}
                  {encounterLogged ? "Logged" : "Pending"}
                </span>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <article className="rounded-md border bg-slate-50 p-3">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-[#162e51]">
                    <ClipboardList className="size-4" /> Call Summary
                  </h3>
                  <p className="mt-2 text-xs text-slate-600">
                    {summaryReady
                      ? "Verified summary evidence available"
                      : "Awaiting verified transcript and summary receipt"}
                  </p>
                </article>
                <article className="rounded-md border bg-slate-50 p-3">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-[#162e51]">
                    <FileText className="size-4" /> Confirmation Letter
                  </h3>
                  <p className="mt-2 text-xs text-slate-600">
                    {receipt?.verifiedReadback
                      ? "Verified synthetic booking read-back available"
                      : "Unavailable without persisted synthetic booking evidence"}
                  </p>
                </article>
              </div>
              <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-10 gap-1"
                  disabled={!receipt?.verifiedReadback}
                  onClick={() => openLetter(false)}
                >
                  <FileDown className="size-4" /> Preview Letter
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-10 gap-1"
                  disabled={!receipt?.verifiedReadback}
                  onClick={() => openLetter(true)}
                >
                  <Printer className="size-4" /> Print / Save PDF
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
