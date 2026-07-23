import { useState } from "react";
import { listRecordings } from "./api";
import LangSwitch from "./components/LangSwitch";
import RecordingsList from "./components/RecordingsList";
import TimelinePanel from "./components/TimelinePanel";
import UploadForm from "./components/UploadForm";
import { usePoll } from "./hooks/usePoll";
import { useI18n } from "./i18n";
import type { RecordingSummary } from "./types";

export default function App() {
  const { t } = useI18n();
  const { data: recordings, error } = usePoll(listRecordings, 2500);
  const [selected, setSelected] = useState<{
    id: string;
    filename: string;
  } | null>(null);

  // Empty state = centered upload hero. Once there's something to show, the
  // hero rises to the top (padding transition) and the table drops in below.
  const hasData = !!recordings && recordings.length > 0;

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-4xl px-6 pb-20">
        <div className="flex items-center justify-end py-4">
          <LangSwitch />
        </div>

        <div
          className={
            "transition-[padding] duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] " +
            (hasData ? "pt-2" : "pt-[22vh]")
          }
        >
          <header className="text-center">
            <h1 className="text-2xl font-bold text-neutral-50">
              YADRO <span className="text-red-500">·</span> {t("appTitle")}
            </h1>
            <p className="mx-auto mt-1 max-w-xl text-sm text-neutral-400">
              {t("appSubtitle")}
            </p>
          </header>

          <div className="mx-auto mt-6 max-w-2xl">
            <UploadForm />
          </div>

          {!hasData && error && (
            <p className="mt-4 text-center text-sm text-neutral-500">
              {t("apiUnreachable", { error })}
            </p>
          )}
        </div>

        {hasData && (
          <div className="animate-fade-in-up mt-10 flex flex-col gap-8">
            <RecordingsList
              recordings={recordings}
              error={error}
              selectedId={selected?.id ?? null}
              onSelect={(r: RecordingSummary) =>
                setSelected({ id: r.id, filename: r.filename })
              }
            />

            {selected && (
              <TimelinePanel id={selected.id} filename={selected.filename} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
