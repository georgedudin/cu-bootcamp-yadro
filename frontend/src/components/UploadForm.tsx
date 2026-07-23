import { useRef, useState } from "react";
import { uploadRecording } from "../api";
import { useI18n } from "../i18n";

export default function UploadForm() {
  const { t } = useI18n();
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
      className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4"
    >
      {/* Two equal columns on wide screens, stacked on mobile. Labels stack
          name+hint and inputs bottom-align (mt-auto), so a long RU hint that
          wraps never knocks the fields out of alignment. */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
          <span className="flex flex-col leading-tight">
            <span className="text-neutral-300">{t("fileLabel")}</span>
            <span className="text-xs text-neutral-600">· {t("fileHint")}</span>
          </span>
          <input
            ref={fileRef}
            type="file"
            accept="audio/mpeg,.mp3"
            required
            className="mt-auto h-9 w-full overflow-hidden rounded-md border border-neutral-700 bg-neutral-950 pr-3 text-sm text-neutral-500 file:mr-4 file:h-full file:cursor-pointer file:border-0 file:bg-neutral-800 file:px-4 file:text-sm file:text-neutral-200 hover:file:bg-neutral-700"
          />
        </label>
        <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
          <span className="flex flex-col leading-tight">
            <span className="text-neutral-300">{t("speakersLabel")}</span>
            <span className="text-xs text-neutral-600">
              · {t("speakersHint")}
            </span>
          </span>
          <input
            type="number"
            min={2}
            value={speakers}
            onChange={(e) => setSpeakers(e.target.value)}
            placeholder={t("speakersPlaceholder")}
            className="mt-auto h-9 w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 text-sm text-neutral-100 placeholder:text-neutral-600"
          />
        </label>
      </div>
      {/* Status sits in the button row (not a new line below) and truncates,
          so the card's height never changes whether or not a message shows. */}
      <div className="mt-4 flex items-center justify-end gap-3">
        {(uploaded || error) && (
          <p
            title={error ? error : uploaded}
            className={
              "min-w-0 flex-1 truncate text-sm " +
              (error ? "text-red-400" : "text-emerald-400")
            }
          >
            {error ? error : t("uploaded", { name: uploaded ?? "" })}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="h-9 shrink-0 rounded-md bg-red-600 px-5 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? t("uploading") : t("upload")}
        </button>
      </div>
    </form>
  );
}
