import { useState } from "react";
import RecordingsList from "./components/RecordingsList";
import TimelinePanel from "./components/TimelinePanel";
import UploadForm from "./components/UploadForm";
import type { RecordingSummary } from "./types";

export default function App() {
  const [selected, setSelected] = useState<{
    id: string;
    filename: string;
  } | null>(null);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold text-neutral-50">
          YADRO <span className="text-red-500">·</span> lecture diarization
        </h1>
        <p className="mt-1 text-sm text-neutral-400">
          Upload a lecture, watch it process chunk-by-chunk, then explore who
          spoke when.
        </p>
      </header>

      <UploadForm />

      <RecordingsList
        selectedId={selected?.id ?? null}
        onSelect={(r: RecordingSummary) =>
          setSelected({ id: r.id, filename: r.filename })
        }
      />

      {selected && (
        <TimelinePanel id={selected.id} filename={selected.filename} />
      )}
    </div>
  );
}
