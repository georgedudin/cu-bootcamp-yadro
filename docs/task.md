# Task — Local ASR + Diarization service for EdTech analytics (YADRO)

> **Case:** Local AI service for speech transcription and diarization for EdTech analytics.
> **Track:** ML · Development · Product
> **Format:** Online, evenings 19:00–22:00.
> **Core stack:** FastAPI · ASR (faster-whisper) · Voice Diarization · HuggingFace.
>
> _Language note: this brief is in English per project convention. The graded
> evaluation criteria are reproduced **verbatim in Russian** at the bottom, since
> they are authoritative for scoring and must not drift in translation._

## Summary

Build a high-performance, fully **local / on-prem** backend service on **FastAPI**
that automatically processes audio recordings of educational lectures and lessons.
The pipeline does **batched, chunk-by-chunk** audio processing:

- **ASR** (speech recognition) with **faster-whisper**, and
- **Voice diarization** (speaker separation),

while preserving **end-to-end speaker identity across the entire recording**.

## Problem

EdTech platforms and methodologists process **terabytes** of lesson audio.

- **Cloud** solutions impose data-privacy constraints and are cost-inefficient.
- **Open-source** solutions often require loading the **entire** audio into memory,
  which crashes services on long lectures.
- **Chunked** processing solves the resource problem but creates the core engineering
  challenge: **not losing unique speaker IDs across isolated chunks.**

## Why it matters for the business

An autonomous (on-prem) audio-analytics service lets EdTech companies seamlessly
label lesson structure, assess student engagement, and monitor teaching quality —
**without sending data to third-party APIs.**

## Candidate requirements

**Required**
- Experience with pretrained AI models (HuggingFace)
- Confident Python and FastAPI
- Understanding of audio handling in Python (librosa, soundfile, pydub)

**Nice to have**
- Docker for containerization
- Understanding of data clustering and vector embeddings

## Evaluation criteria (graded)

**Excellent.** The system autonomously determines the **exact** number of unique
speakers: **N students + 1 teacher**. An end-to-end embedding-matching algorithm
across chunks keeps a **specific** student's ID stable throughout the whole lecture.

**Good.** The system determines several speakers and, in most cases, correctly
preserves their IDs across chunks. Occasional matching errors are possible, but the
overall timeline stays coherent and analyzable.

**Satisfactory.** The FastAPI service reliably accepts audio, splits it into chunks,
and transcribes via faster-whisper **without running out of memory**. A **binary**
speech split is implemented: teacher vs. students. A demo interface visualizes the
timeline.

## Learning outcomes ("you will learn to…")

- Build production-ready AI services on FastAPI with **batched streaming** audio processing
- Integrate ASR models (e.g. faster-whisper) into audio pipelines and **optimize for memory**
- Separate speakers and extract **voice embeddings**
- Use end-to-end tracking + clustering to **preserve context across chunks**
- Work with audio in Python: sampling, frames, and formats via librosa / soundfile / pydub
- Optimize and **containerize** ML services for **on-prem** deployment

## Not provided in the source brief

The original case page also lists these sections, but no content was supplied:
**mentors**, **bootcamp results/logistics detail**, **FAQ**. Fill in when available.

---

## Source — original evaluation criteria (RU, verbatim, authoritative)

> **«Отлично»**
> Система самостоятельно определяет точное количество уникальных спикеров: N студентов
> и 1 учитель. Реализован алгоритм сквозного сопоставления эмбеддингов между чанками,
> поэтому ID конкретного студента сохраняется на протяжении всей лекции.
>
> **«Хорошо»**
> Система определяет несколько спикеров и в большинстве случаев корректно сохраняет их
> ID между чанками. Возможны отдельные ошибки сопоставления, но общий таймлайн остается
> понятным и пригодным для анализа.
>
> **«Удовлетворительно»**
> Сервис на FastAPI стабильно принимает аудио, делит его на чанки и транскрибирует через
> faster-whisper без падения по памяти. Реализовано бинарное разделение речи: учитель и
> студенты. Демо-интерфейс визуализирует таймлайн.
