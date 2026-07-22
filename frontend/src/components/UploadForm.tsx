import { useRef, useState } from "react";
import { uploadRecording } from "../api";

export default function UploadForm() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [speakers, setSpeakers] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [uploaded, setUploaded] = useState<string>();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(undefined);
    setUploaded(undefined);
    try {
      await uploadRecording(file, speakers === "" ? null : Number(speakers));
      setUploaded(file.name);
      if (fileRef.current) fileRef.current.value = "";
      setSpeakers("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-4 rounded-xl border border-neutral-800 bg-neutral-900/60 p-4"
    >
      <label className="flex flex-col gap-1 text-sm text-neutral-400">
        Lecture audio (mp3)
        <input
          ref={fileRef}
          type="file"
          accept="audio/mpeg,.mp3"
          required
          className="text-sm text-neutral-200 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-700 file:px-3 file:py-1.5 file:text-sm file:text-neutral-100 hover:file:bg-neutral-600"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-neutral-400">
        Expected speakers (optional, incl. teacher)
        <input
          type="number"
          min={2}
          value={speakers}
          onChange={(e) => setSpeakers(e.target.value)}
          placeholder="e.g. 13"
          className="w-44 rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm"
        />
      </label>
      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
      >
        {busy ? "Uploading…" : "Upload"}
      </button>
      {uploaded && (
        <span className="text-sm text-emerald-400">✓ {uploaded} uploaded</span>
      )}
      {error && <span className="text-sm text-red-400">{error}</span>}
    </form>
  );
}
