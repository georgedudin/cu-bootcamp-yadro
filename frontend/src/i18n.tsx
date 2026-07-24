import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// Lightweight, dependency-free i18n. UI copy only — the wire contract
// (types, endpoints, status *values*) is untouched; we localize display
// labels via `st_<status>` keys keyed off the backend's stable enum.
export type Lang = "en" | "ru";
type Params = Record<string, string | number>;
type Dict = Record<string, string>;

const en: Dict = {
  appTitle: "lecture transcripts",
  appSubtitle:
    "Upload a lecture, watch it process chunk-by-chunk, then explore who spoke when.",
  fileLabel: "Lecture audio",
  fileHint: "mp3",
  chooseFile: "Choose file",
  noFileSelected: "no file selected",
  speakersLabel: "Expected speakers",
  speakersHint: "optional, incl. teacher",
  speakersPlaceholder: "e.g. 13",
  upload: "Upload",
  uploading: "Uploading…",
  uploaded: "✓ {name} uploaded",
  apiUnreachable: "Can't reach the API: {error}",
  colFile: "File",
  colUploaded: "Uploaded",
  colDuration: "Duration",
  colRtf: "RTF",
  colRtfHint: "Real-time factor: processing time ÷ audio length (lower is faster)",
  colStatus: "Status",
  refreshFailing: "Refresh failing ({error}) — showing last known state.",
  timelineError: "Couldn't load the timeline: {error}",
  loadingTimeline: "Loading timeline…",
  silence: "Silence",
  speakerTeacher: "Teacher",
  speakerStudent: "Student #{n}",
  nowPlaying: "Now playing ↓",
  cleanup: "Delete all",
  cleanupConfirm:
    "Delete ALL recordings, audio files and transcripts (even those still processing)? This cannot be undone.",
  st_uploaded: "uploaded",
  st_queued: "queued",
  st_processing: "processing",
  st_stitching: "stitching",
  st_done: "done",
  st_failed: "failed",
};

const ru: Dict = {
  appTitle: "расшифровка лекций",
  appSubtitle:
    "Загрузите лекцию, следите за обработкой по фрагментам и смотрите, кто и когда говорил.",
  fileLabel: "Аудио лекции",
  fileHint: "mp3",
  chooseFile: "Выбрать файл",
  noFileSelected: "файл не выбран",
  speakersLabel: "Ожидается говорящих",
  speakersHint: "необязательно, включая преподавателя",
  speakersPlaceholder: "напр. 13",
  upload: "Загрузить",
  uploading: "Загрузка…",
  uploaded: "✓ {name} загружен",
  apiUnreachable: "Нет связи с API: {error}",
  colFile: "Файл",
  colUploaded: "Загружено",
  colDuration: "Длительность",
  colRtf: "RTF",
  colRtfHint: "Коэффициент реального времени: время обработки ÷ длительность аудио (меньше — быстрее)",
  colStatus: "Статус",
  refreshFailing: "Ошибка обновления ({error}) — показано последнее состояние.",
  timelineError: "Не удалось загрузить таймлайн: {error}",
  loadingTimeline: "Загрузка таймлайна…",
  silence: "Тишина",
  speakerTeacher: "Преподаватель",
  speakerStudent: "Студент №{n}",
  nowPlaying: "Сейчас играет ↓",
  cleanup: "Удалить всё",
  cleanupConfirm:
    "Удалить ВСЕ записи, аудиофайлы и расшифровки (включая ещё обрабатываемые)? Это действие необратимо.",
  st_uploaded: "загружено",
  st_queued: "в очереди",
  st_processing: "обработка",
  st_stitching: "сборка",
  st_done: "готово",
  st_failed: "ошибка",
};

const DICTS: Record<Lang, Dict> = { en, ru };

type I18n = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, params?: Params) => string;
  // Localized display label for a wire speaker id ('teacher', 'student_1', …).
  // The id itself is never mutated — this is display-only, like the st_* keys.
  speaker: (id: string) => string;
};

const I18nContext = createContext<I18n | null>(null);
const STORAGE_KEY = "yadro.lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "ru") return saved;
  } catch {
    // localStorage unavailable (private mode / SSR) — fall through
  }
  return "ru";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // best-effort persistence
    }
  }, [lang]);

  const value = useMemo<I18n>(() => {
    const dict = DICTS[lang];
    const t = (key: string, params?: Params) => {
      let s = dict[key] ?? key;
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          s = s.replace(`{${k}}`, String(v));
        }
      }
      return s;
    };
    const speaker = (id: string) => {
      if (id === "teacher") return t("speakerTeacher");
      const m = /^student_(\d+)$/.exec(id);
      return m ? t("speakerStudent", { n: m[1] }) : id;
    };
    return { lang, setLang, t, speaker };
  }, [lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
