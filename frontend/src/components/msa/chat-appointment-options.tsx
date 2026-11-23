import { CalendarDays, Clock3, MapPin, Stethoscope } from "lucide-react";
import type { VoiceAppointmentOptions } from "@/lib/voice-appointment-options";

export function ChatAppointmentOptions({
  data,
  current,
}: {
  data: VoiceAppointmentOptions;
  current: boolean;
}) {
  const date = (value: string, options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat("en-US", { ...options, timeZone: data.patient_time_zone }).format(
      new Date(value),
    );
  return (
    <section
      aria-label="Appointment options in your time zone"
      className="rounded-xl border border-border bg-card p-4 shadow-sm"
    >
      <div className="flex items-center gap-2 text-primary">
        <CalendarDays className="size-5" aria-hidden="true" />
        <h3 className="font-semibold">Your appointment options</h3>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {current
          ? "Tell Avery which option you prefer. Nothing is booked until you confirm."
          : "Earlier options — refer to Avery’s latest readback."}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Appointment local time: {data.patient_time_zone.replaceAll("_", " ")}
      </p>
      {data.options.length === 0 ? (
        <p className="mt-4 text-sm">No verified appointments match these preferences.</p>
      ) : (
        <ol className="mt-4 grid gap-3 sm:grid-cols-2">
          {data.options.map((o, index) => (
            <li
              key={o.option_id}
              className="overflow-hidden rounded-lg border border-border bg-background"
            >
              <div className="flex items-center gap-3 border-b border-border bg-primary/5 p-3">
                <div className="rounded-lg bg-primary px-3 py-2 text-center text-primary-foreground">
                  <div className="text-[10px] uppercase">
                    {date(o.begins_at, { month: "short" })}
                  </div>
                  <div className="text-2xl font-bold">{date(o.begins_at, { day: "numeric" })}</div>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Option {index + 1}</p>
                  <p className="font-semibold">{date(o.begins_at, { weekday: "long" })}</p>
                  <p className="text-xs">Primary Care</p>
                </div>
              </div>
              <dl className="space-y-3 p-3 text-sm">
                <div>
                  <dt className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock3 className="size-3.5" />
                    Time
                  </dt>
                  <dd className="mt-1 font-medium">
                    {date(o.begins_at, {
                      hour: "numeric",
                      minute: "2-digit",
                      timeZoneName: "short",
                    })}
                    –{date(o.ends_at, { hour: "numeric", minute: "2-digit" })}
                  </dd>
                </div>
                <div>
                  <dt className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Stethoscope className="size-3.5" />
                    Care provider
                  </dt>
                  <dd>{o.provider_name ?? "Provider not supplied by the scheduling source"}</dd>
                </div>
                <div>
                  <dt className="flex items-center gap-2 text-xs text-muted-foreground">
                    <MapPin className="size-3.5" />
                    Clinic
                  </dt>
                  <dd>{o.facility_name ?? o.clinic_name ?? "Clinic details unavailable"}</dd>
                </div>
              </dl>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-[11px] text-muted-foreground">
        Demo appointment inventory · No VA production booking
      </p>
    </section>
  );
}
