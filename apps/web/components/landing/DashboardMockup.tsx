import { BellIcon, CheckCircleIcon, ClipboardCheckIcon } from "@/components/landing/icons";

// Composition UI purement illustrative — aucun appel API, aucune donnée réelle. Les chiffres et
// noms ci-dessous sont fictifs et génériques par construction (pas une vraie école, pas de vraies
// statistiques présentées comme telles), conformément à la consigne.

function MockStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2.5">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="text-lg font-bold text-brand-text">{value}</p>
    </div>
  );
}

function MockNotifRow({ icon, text, time }: { icon: React.ReactNode; text: string; time: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg px-2 py-1.5">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-blue/10 text-brand-blue">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-brand-text">{text}</p>
      </div>
      <span className="shrink-0 text-[11px] text-slate-400">{time}</span>
    </div>
  );
}

const WEEK_BARS = [40, 65, 50, 80, 60, 92, 70];
const WEEKDAY_LABELS = ["L", "M", "M", "J", "V", "S", "D"];

export function DashboardMockup() {
  return (
    <div className="relative mx-auto max-w-md lg:max-w-none">
      <div
        aria-hidden="true"
        className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-brand-blue/20 to-brand-cyan/20 blur-2xl"
      />

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-brand-blue" />
            <span className="text-xs font-semibold text-slate-500">Tableau de bord — École Les Palmiers</span>
          </div>
          <span className="hidden text-xs text-slate-400 sm:inline">Aujourd&apos;hui</span>
        </div>

        <div className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-4">
          <MockStat label="Élèves actifs" value="428" />
          <MockStat label="Présence" value="96%" />
          <MockStat label="Notes saisies" value="87%" />
          <MockStat label="Bulletins" value="12" />
        </div>

        <div className="grid grid-cols-1 gap-4 px-5 pb-5 sm:grid-cols-5">
          <div className="col-span-3 rounded-xl border border-slate-100 p-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Activité de la semaine
            </p>
            <div className="flex h-20 items-end gap-2">
              {WEEK_BARS.map((h, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-t bg-gradient-to-t from-brand-blue to-brand-cyan"
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
          </div>

          <div className="col-span-2 rounded-xl border border-slate-100 p-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Cette semaine</p>
            <div className="grid grid-cols-7 gap-1 text-center">
              {WEEKDAY_LABELS.map((d, i) => (
                <span key={`label-${i}`} className="text-[9px] text-slate-400">
                  {d}
                </span>
              ))}
              {Array.from({ length: 7 }).map((_, i) => (
                <span
                  key={`day-${i}`}
                  className={`rounded py-1 text-[11px] ${
                    i === 3 ? "bg-brand-blue font-semibold text-white" : "text-slate-600"
                  }`}
                >
                  {10 + i}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-1 border-t border-slate-100 px-5 py-4">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Activité récente</p>
          <MockNotifRow
            icon={<ClipboardCheckIcon className="h-3.5 w-3.5" />}
            text="Présences enregistrées — CE2 B"
            time="Il y a 12 min"
          />
          <MockNotifRow
            icon={<BellIcon className="h-3.5 w-3.5" />}
            text="Bulletin publié — Terminale A"
            time="Il y a 1 h"
          />
        </div>
      </div>

      <div
        aria-hidden="true"
        className="absolute -left-6 top-10 hidden animate-float rounded-xl border border-slate-100 bg-white px-4 py-3 shadow-lg motion-reduce:animate-none sm:block"
        style={{ animationDelay: "0.4s" }}
      >
        <div className="flex items-center gap-2">
          <CheckCircleIcon className="h-5 w-5 text-brand-blue" />
          <div>
            <p className="text-xs font-semibold text-brand-text">Présence à jour</p>
            <p className="text-[11px] text-slate-400">32 classes</p>
          </div>
        </div>
      </div>

      <div
        aria-hidden="true"
        className="absolute -right-4 bottom-8 hidden animate-float rounded-xl border border-slate-100 bg-white px-4 py-3 shadow-lg motion-reduce:animate-none sm:block"
        style={{ animationDelay: "1.1s" }}
      >
        <div className="flex items-center gap-2">
          <BellIcon className="h-5 w-5 text-brand-cyan" />
          <div>
            <p className="text-xs font-semibold text-brand-text">3 notifications</p>
            <p className="text-[11px] text-slate-400">Nouveaux messages</p>
          </div>
        </div>
      </div>
    </div>
  );
}
