import { useI18n, type Lang } from "../i18n";

const LANGS: { code: Lang; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "ru", label: "RU" },
];

export default function LangSwitch() {
  const { lang, setLang } = useI18n();
  return (
    <div className="inline-flex items-center rounded-full border border-neutral-800 bg-neutral-900/60 p-0.5 text-xs font-medium">
      {LANGS.map((l) => (
        <button
          key={l.code}
          type="button"
          onClick={() => setLang(l.code)}
          aria-pressed={lang === l.code}
          className={
            "rounded-full px-3 py-1 transition-colors " +
            (lang === l.code
              ? "bg-neutral-700 text-neutral-50"
              : "text-neutral-400 hover:text-neutral-200")
          }
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
