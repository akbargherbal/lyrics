# خطة قاعدة بيانات كلمات الأغاني العربية

> الهدف: قاعدة بيانات شخصية (غير تجارية) لأهم الفنانين العرب، تحتوي على أكبر عدد ممكن من الكلمات، مع دعم الكلمات المتزامنة (LRC) لتطبيق كاريوكي/تعلّم العربية لاحقاً.  
> المبدأ: نخزّن كل نسخة نجدها من كل مصدر، ثم نختار «النسخة المفضّلة» لكل أغنية، ونحتفظ دائماً بمصدر كل نص.

---

## 0) الملخص التنفيذي

- **القاعدة الأساسية:** SQLite كقاعدة بيانات قانونية (Canonical DB)، وJSON كملف تصدير للتطبيق.
- **المصادر الرئيسية:**
  - **LyricFind Catalog API** → قائمة الأغاني، الألبوم، المدة، مقتطف (وليس النص الكامل).
  - **fnanen.com** و **kalimataghani.com** → نصوص عربية كاملة (بدون تزامن).
  - **LRCLIB** → نصوص كاملة + نصوص متزامنة LRC (وأحياناً word-level).
  - **iTunes Search API / MusicBrainz** → ديسكوغرافيا ومدة وألبومات.
  - **Tarab** → احتياطي عربي (نص على مستوى المقطع، بدون تزامن).
- **ما لا نفعله:** لا نحاول تجاوز الحجب (403) على صفحات LyricFind، ولا نعيد نشر الكلمات.
- **الواجهة في الصورة** تحتاج تحديداً: `title`, `duration`, `has_synced`, `instrumental`, `album`, `artist`. الخطة تجعل هذه الحقول متاحة مباشرة في التصدير.

---

## 1) الأصول الموجودة حالياً

| الأصل | المحتوى | ملاحظات |
|---|---|---|
| `fnanen/` | إليسا 112 أغنية، فضل شاكر 76 أغنية | نص كامل + كلمات/ألحان/سنة، بدون تزامن |
| `kalimataghani/` | إليسا 46، فضل شاكر 26 | نص كامل مع التشكيل كما نُشر |
| `fadel_chaker_lyrics.json` | 255 أغنية، 142 نص كامل | من LyricFind + LRCLIB، لكن **بدون حقل synced** |
| `fadel-chaker-lyrics-scraper.json` | محادثة/سياق العمل السابق | مرجع للمنهجية والقرارات |

### الفجوات الحالية

1. كل مشروع له Schema مختلف.
2. لا يوجد فهرس موحّد للفنانين (Aliases، روابط المواقع، IDs).
3. لا يوجد حقل `lyrics_synced` في ملف فضل شاكر.
4. لا يوجد Dedup بين المصادر (أغنية واحدة قد تظهر 3 مرات).
5. لا يوجد تقرير تغطية (كم أغنية عندها كلمات؟ كم منها متزامن؟).
6. لا يوجد جدول `missing` لمتابعة النواقص.

---

## 2) نطاق المرحلة الأولى

### القائمة النهائية (37 فناناً)

اعتُمدت القائمة النهائية في `artists_final.txt`، وسجلها الآلي في `artists.yaml`.

- **Tier 1 (10):** ماجد المهندس، إليسا، عمرو دياب، رابح صقر، عبد المجيد عبد الله، أصالة، وليد الشامي، نجوى كرم، وائل كفوري، نوال الكويتية.
- **Tier 2 (15):** تامر حسني، كاظم الساهر، حسين الجسمي، أميمة طالب، عاصي الحلاني، فضل شاكر، أسماء لمنور، شيرين عبد الوهاب، صابر الرباعي، ملحم زين، مروان خوري، نبيل شعيل، هيفاء وهبي، بلقيس، نوال الزغبي.
- **Tier 3 (12):** جابر الكاسر، راشد الماجد، نانسي عجرم، عبد الله الرويشد، محمد البلوشي، عبادي الجوهر، محمد عبده، طلال مداح، لطيفة، مايا نصري، ماجدة الرومي، محمد حماقي.

> ملاحظة: فضل شاكر وإليسا لديهما بيانات أولية، لذا يمكن البدء بهما فوراً حتى لو كان ترتيبهما في Tier 2/Tier 1.

### سجل الفنانين `artists.yaml`

- `rank`: ترتيب الاختيار.
- `tier`: 1/2/3.
- `shortlist_no`: رقمه في القائمة السابقة (للرجوع).
- `aliases`: أسماء بديلة عربية/لاتينية.
- `lyricfind_slug`, `itunes_artist_id`, `musicbrainz_id`, `fnanen_url`, `kalimataghani_url`: تُملأ في مرحلة Discovery.

> ملاحظة: الروابط الفارغة تُملأ في مرحلة Discovery، وليست افتراضات.

---

## 3) المعمارية العامة

```text
artists.yaml
     │
     ▼
┌─────────────────────────────────────────────┐
│ 1. Catalog Collectors                       │
│ LyricFind API + iTunes + MusicBrainz        │
│ + fnanen/kalimataghani listings             │
└─────────────────────────────────────────────┘
     │  raw catalog
     ▼
┌─────────────────────────────────────────────┐
│ 2. Normalizer + Deduper                     │
│ Arabic normalization, aliases, duration     │
└─────────────────────────────────────────────┘
     │  canonical songs
     ▼
┌─────────────────────────────────────────────┐
│ 3. Lyrics Collectors                        │
│ LRCLIB (synced/plain) + fnanen +            │
│ kalimataghani + Tarab + manual              │
└─────────────────────────────────────────────┘
     │  lyric candidates
     ▼
┌─────────────────────────────────────────────┐
│ 4. Matcher + Scorer                         │
│ title/artist/duration/album → confidence    │
└─────────────────────────────────────────────┘
     │  preferred + alternates
     ▼
┌─────────────────────────────────────────────┐
│ 5. SQLite Canonical DB                      │
│ artists / songs / lyrics / sources / missing│
└─────────────────────────────────────────────┘
     │
     ├── export/artists/<artist>.json
     ├── export/combined.json
     ├── export/missing.json
     └── export/report.csv
```

**لماذا SQLite؟**

- استعلامات سريعة بالعربي والإنجليزي.
- FTS5 للبحث في الكلمات.
- سهولة التصدير إلى JSON.
- لا تحتاج سيرفراً.
- يمكن فتحها بأي أداة.

---

## 4) نموذج البيانات (SQLite)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE artists (
    id              INTEGER PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    name_ar         TEXT NOT NULL,
    name_en         TEXT,
    country         TEXT,
    lyricfind_slug  TEXT,
    itunes_id       TEXT,
    musicbrainz_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE artist_aliases (
    id          INTEGER PRIMARY KEY,
    artist_id   INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    normalized  TEXT NOT NULL,
    UNIQUE(artist_id, normalized)
);

CREATE TABLE songs (
    id               INTEGER PRIMARY KEY,
    artist_id        INTEGER NOT NULL REFERENCES artists(id),
    canonical_key    TEXT NOT NULL UNIQUE,
    title_ar         TEXT,
    title_en         TEXT,
    normalized_title TEXT NOT NULL,
    album            TEXT,
    duration_sec     INTEGER,
    year             TEXT,
    isrc             TEXT,
    language         TEXT DEFAULT 'ar',
    instrumental     INTEGER NOT NULL DEFAULT 0,
    version          TEXT DEFAULT 'studio',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE song_sources (
    id            INTEGER PRIMARY KEY,
    song_id       INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    source        TEXT NOT NULL,          -- lyricfind | itunes | musicbrainz | fnanen | kalimataghani | lrclib
    source_id     TEXT,
    source_url    TEXT,
    raw_title     TEXT,
    raw_artist    TEXT,
    raw_duration  INTEGER,
    payload_json  TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE lyrics (
    id              INTEGER PRIMARY KEY,
    song_id         INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,        -- lrclib | fnanen | kalimataghani | tarab | manual
    source_id       TEXT,
    source_url      TEXT,
    kind            TEXT NOT NULL,        -- plain | synced | word_synced
    format          TEXT NOT NULL,        -- text | lrc | yaml
    text            TEXT NOT NULL,
    line_count      INTEGER,
    has_synced      INTEGER NOT NULL DEFAULT 0,
    has_word_sync   INTEGER NOT NULL DEFAULT 0,
    match_score     REAL,
    match_method    TEXT,
    is_preferred    INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(song_id, source, source_id, kind)
);

CREATE TABLE missing (
    id            INTEGER PRIMARY KEY,
    song_id       INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    reason        TEXT NOT NULL,          -- no_match | low_confidence | blocked | bad_metadata
    last_attempt  TEXT NOT NULL DEFAULT (datetime('now')),
    notes         TEXT
);

CREATE INDEX idx_songs_artist      ON songs(artist_id);
CREATE INDEX idx_songs_norm_title  ON songs(normalized_title);
CREATE INDEX idx_lyrics_song       ON lyrics(song_id);
CREATE INDEX idx_lyrics_preferred  ON lyrics(song_id, is_preferred);
CREATE INDEX idx_song_sources_song ON song_sources(song_id);

CREATE VIRTUAL TABLE lyrics_fts USING fts5(
    title_ar, title_en, artist_ar, artist_en, lyrics_text,
    content=''
);
```

### قواعد مهمة

- `songs.canonical_key` = hash من `(artist_id, normalized_title, duration_bucket)`.
- `lyrics.is_preferred` = نسخة واحدة فقط لكل أغنية.
- نحتفظ بكل النسخ الأخرى كـ `alternates`.
- `instrumental` يأتي من LRCLIB أو من حقل صريح.
- `has_synced` و`has_word_sync` يُشتقّان من النص، وليسا تخميناً.

---

## 5) استراتيجية المصادر

| المصدر | الاستخدام | ما يقدّمه | القيود |
|---|---|---|---|
| **LyricFind Catalog API** | قائمة أغاني + Metadata | title, duration, album, snippet, lfid | لا يعطي النص الكامل؛ صفحات `/lyrics/*` محجوبة 403 |
| **iTunes Search API** | ديسكوغرافيا | title, artist, album, duration, ISRC | حد 200 نتيجة/طلب؛ يحتاج تقسيم بالألبومات |
| **MusicBrainz** | تحقق من الهوية | aliases, releases, IDs | Rate limit ~1 req/s + User-Agent |
| **fnanen.com** | نص عربي كامل | lyrics, lyricist, composer, year | لا يوجد تزامن؛ يحتاج رابط فنان |
| **kalimataghani.com** | نص عربي كامل | lyrics مع التشكيل | لا يوجد تزامن؛ يحتاج رابط فنان |
| **LRCLIB API** | نص + تزامن | plainLyrics, syncedLyrics, duration, instrumental | Crowd-sourced؛ بحث 20 نتيجة؛ Rate limit |
| **LRCLIB Dump** | Bulk | كل السجلات | ~46 GiB مضغوط؛ يحتاج مساحة |
| **Tarab** | احتياطي عربي | Verse-level lyrics | لا تزامن؛ بحثي؛ قد يخلط الشعر |
| **LRCGET** | أداة محلية | تنزيل LRC لمكتبة صوتية | ليست مصدراً بحد ذاته |

### أولوية الكلمات

لكل أغنية:

1. **LRCLIB synced** → أفضل خيار للكاريوكي.
2. **fnanen / kalimataghani** → نص عربي كامل (مفضّل على LRCLIB plain إذا كان أنظف/أكمل).
3. **LRCLIB plain** → نص كامل بدون تزامن.
4. **Tarab** → احتياطي عربي.
5. **مراجعة يدوية** → للأغاني المهمة فقط.

مع الاحتفاظ بكل النسخ، وليس حذف غير المفضّل.

---

## 6) خط أنابيب الجمع (Pipeline)

### الخطوة 0: سجل الفنانين

- إنشاء `artists.yaml`.
- لكل فنان: الاسم العربي، اللاتيني، Aliases، الدولة، روابط المصادر.
- التحقق من وجود الفنان في LyricFind/iTunes/fnanen/kalimataghani.

### الخطوة 1: جمع الكتالوج

لكل فنان:

- LyricFind: `/api/v1/charts?reqtype=trackcharts&artistid=slug:<slug>&limit=100&offset=...`
- iTunes: `term=<artist>&entity=song&limit=200&country=...`
- إذا تجاوز 200: جلب الألبومات ثم أغاني كل ألبوم.
- fnanen/kalimataghani: تشغيل الـ scrapers الموجودة.

الناتج: `raw/<artist>/catalog.json`.

### الخطوة 2: التنظيف والتوحيد

- تطبيع العربية (انظر القسم 7).
- توحيد صيغ المدة: `3:25` → `205`.
- استخراج `title_ar`, `title_en`, `album`, `duration_sec`.
- دمج التكرارات داخل نفس المصدر.
- إنشاء `canonical_key`.
- عدم دمج النسخ المختلفة (Live/Remix) إلا بوجود سبب.

الناتج: `songs` في SQLite.

### الخطوة 3: جمع الكلمات

لكل أغنية:

```text
LRCLIB /api/get (artist, title, duration)
    ├── نجح → خزّن plain + synced
    └── فشل → LRCLIB /api/search (عربي/لاتيني)
                ├── نجح → طابق وقيّم
                └── فشل → fnanen / kalimataghani
                            ├── نجح → خزّن plain
                            └── فشل → Tarab → manual
```

#### LRCLIB `/api/get`

```bash
curl -G "https://lrclib.net/api/get" \
  --data-urlencode "artist_name=Fadel Chaker" \
  --data-urlencode "track_name=معقول" \
  --data-urlencode "duration=236" \
  -H "User-Agent: ArabicLyricsDB/1.0 (personal use)"
```

- المدة مهمة: `/api/get` يطابق ±2 ثانية.
- إذا كانت المدة غير مؤكدة، استخدم `/api/search` ثم طابق يدوياً.
- خزّن `syncedLyrics` و`plainLyrics` و`instrumental`.

#### fnanen / kalimataghani

- استخدم الـ scrapers الحالية.
- خزّن `source_url` و`lyricist` و`composer` و`year` إن وجدت.
- لا تعتمد على ترتيب الأغاني؛ استخدم التطبيع.

### الخطوة 4: المطابقة والتقييم

انظر القسم 7.

### الخطوة 5: التخزين

- إدخال/تحديث SQLite.
- `is_preferred` واحد فقط.
- `missing` لكل أغنية بلا نص.
- `report` بالإحصاءات.

### الخطوة 6: التصدير

- `export/artists/<slug>.json`
- `export/combined.json`
- `export/missing.json`
- `export/report.csv`

---

## 6.1) Batch Job للـ VM

تم تجهيز Job قابل للتشغيل على VM لمدة 1–2 ساعة:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r batch/requirements.txt
python -m batch.job --config batch/config.yaml --minutes 120
```

ما يفعله:

1. يستورد البيانات الموجودة (fnanen / kalimataghani / LyricFind+LRCLIB).
2. ينظّف النصوص ويحسب `quality_score` و`quality_flags`.
3. يجلب أغاني إضافية من iTunes وLRCLIB ضمن ميزانية الوقت.
4. ينتج `review/candidates.csv` و`review/review_queue.csv` و`review/songs.csv` و`review/summary.md`.
5. يحفظ التقدم في SQLite ويمكن استئنافه.

التفاصيل الكاملة: `batch/README.md`.

---

## 6.2) النسخ الاحتياطي والاستعادة والاستئناف

### المسار والأدوات

- **النسخ الاحتياطي:** `gs://akbar-december-2024-backup/lyrics/`
- **السكربت:** `batch/backup_gcs.sh`
- **دليل مختصر:** `batch/BACKUP.md`
- **السجل:** `batch/backup.log`

### آلية العمل

- يعمل كعملية منفصلة تماماً عن `python -m batch.job`، فلا يوقف الـ Job ولا يتأثر به.
- ينسخ كل **15 دقيقة** افتراضياً (`BACKUP_INTERVAL_SECONDS`).
- يستخدم **SQLite Online Backup API**، لذا يلتقط نسخة متسقة حتى مع وجود `-wal` و`-shm` أثناء الكتابة.
- يرفع:
  - `latest/lyrics.db.gz` — أحدث نسخة من القاعدة (مضغوطة).
  - `latest/review/` — حزمة المراجعة كاملة.
  - `latest/logs/` — `run.log` و`nohup.out` و`backup.log`.
  - `latest/meta/` — نسخة من `PLAN.md` و`PROGRESS.md` و`artists.yaml` و`schema.sql` وكود/إعدادات الـ pipeline، حتى لا تعتمد الاستعادة على بقاء الـ VM.
  - `latest/manifest.json` — إحصاءات، الفنان الحالي، التقدم، وcommit.
  - `snapshots/YYYYMMDDTHHMMSSZ/` — نسخة ثابتة لكل دورة، لا تُحذف تلقائياً.
- لا ينسخ `batch/cache/` لأنه قابل لإعادة التوليد؛ القاعدة نفسها تحفظ كل التقدم المهم.
- يتوقف تلقائياً بعد دورتين متتاليتين بدون Job (حوالي 30 دقيقة)، مع ترك آخر نسخة.

### التشغيل والتحقق

```bash
# نسخة واحدة فورية (للاختبار)
bash batch/backup_gcs.sh --once

# حلقة النسخ الدورية في الخلفية
nohup bash batch/backup_gcs.sh >/dev/null 2>&1 &

# التحقق
gcloud --quiet storage ls -r gs://akbar-december-2024-backup/lyrics/ | head -30
gcloud --quiet storage cat gs://akbar-december-2024-backup/lyrics/latest/manifest.json
```

- المتطلب الوحيد: `gcloud auth login` بحساب يملك صلاحية الكتابة على الـ bucket.
- إذا كان `gcloud config get-value project` فارغاً فهذا لا يمنع الوصول إلى bucket محدد.
- يمكن تغيير الوجهة أو الفاصل الزمني:

```bash
BACKUP_BUCKET=gs://another-bucket/lyrics BACKUP_INTERVAL_SECONDS=600 \
  nohup bash batch/backup_gcs.sh >/dev/null 2>&1 &
```

### الاستعادة

> **مهم:** القاعدة تعمل بـ WAL. لا تنسخ `data/lyrics.db` وحدها أثناء تشغيل الـ Job. استخدم النسخة المرفوعة، أو أوقف الـ Job أولاً.

```bash
# 1) تأكد من إيقاف الـ Job (أو أوقفه بأمان)
pkill -f "python -m batch.job"

# 2) احذف ملفات WAL القديمة قبل الاستعادة
rm -f data/lyrics.db data/lyrics.db-wal data/lyrics.db-shm

# 3) نزّل أحدث نسخة وفك ضغطها
gcloud storage cp gs://akbar-december-2024-backup/lyrics/latest/lyrics.db.gz /tmp/lyrics.db.gz
gunzip -c /tmp/lyrics.db.gz > data/lyrics.db

# 4) استعد حزمة المراجعة
rm -rf review
gcloud storage cp -r gs://akbar-december-2024-backup/lyrics/latest/review ./review
```

لاستعادة لحظة محددة بدل `latest`:

```bash
gcloud storage cp gs://akbar-december-2024-backup/lyrics/snapshots/YYYYMMDDTHHMMSSZ/lyrics.db.gz /tmp/lyrics.db.gz
```

### الاستئناف بعد التوقف

- أعد تشغيل نفس الأمر:

```bash
source .venv/bin/activate
python -m batch.job --config batch/config.yaml --minutes 120
```

- الـ Job يقرأ `completed_artists` من `job_state` ويتخطى الفنانين المكتملين.
- إذا توقف في منتصف فنان، يعيد ذلك الفنان من البداية مع الاستفادة من `batch/cache/`.
- `--force` لإعادة معالجة الفنانين المكتملين أيضاً.
- كل تشغيل يصدّر حزمة مراجعة جديدة في `review/`، حتى لو لم يكتمل كل الفنانين.
- بعد الاستعادة من نسخة احتياطية، شغّل الـ Job بنفس الأمر؛ سيستأنف من آخر حالة محفوظة في القاعدة.

### قائمة فحص بعد أي انقطاع

1. تأكد هل الـ Job ما زال يعمل: `pgrep -af "python -m batch.job"`.
2. إذا فُقدت القاعدة أو تلفت، استعد من `latest/` أو من snapshot محدد.
3. أعد تشغيل الـ Job بنفس الأمر.
4. تأكد أن حلقة النسخ الاحتياطي تعمل: `pgrep -af backup_gcs.sh`؛ أعد تشغيلها إذا لزم.
5. راقب `batch/run.log` و`batch/nohup.out`، ثم راجع `review/summary.md`.

### ما لا نفعله

- لا نحذف `data/` أو `review/` أثناء التشغيل.
- لا ننسخ القاعدة بطريقة غير متسقة أثناء WAL.
- لا نرفع شيئاً إلى GitHub إلا بطلب صريح.
- لا نحاول تجاوز حجب LyricFind (403).

---

## 7) التطبيع والمطابقة

### تطبيع العربية

```text
1. احذف التشكيل: ً ٌ ٍ َ ُ ِ ّ ْ
2. احذف التطويل: ـ
3. وحّد الألف: أ إ آ ٱ → ا
4. وحّد الياء: ى → ي
5. وحّد التاء المربوطة: ة → ه
6. احذف علامات الترقيم
7. وحّد المسافات
8. حوّل الأرقام العربية → لاتينية
```

### تطبيع اللاتيني

- lowercase
- إزالة علامات الترقيم
- إزالة `(feat. ...)` من العنوان للمطابقة فقط

### هوية الفنان والأسماء البديلة

الفنان الواحد قد يظهر بأشكال كثيرة:

```text
Fadl Shaker
Fadel Shaker
Fadhl Chaker
Fadhel Shaker
Fadhl Shaker
```

لذلك نستخدم طبقتين:

1. **`aliases` في `artists.yaml`**: قائمة يدوية بالأشكال الشائعة.
2. **`latin_key`**: مفتاح transliteration تقريبي يوحّد:

```text
ch → sh
kh → k
dh → d
th → t
ph → f
q  → k
حذف حروف العلة a/e/i/o/u/y
```

أمثلة:

| الاسم | المفتاح |
|---|---|
| Fadel Shaker | `fdl shkr` |
| Fadhl Chaker | `fdl shkr` |
| Fadhel Shaker | `fdl shkr` |
| Majid Al Mohandis | `mjd l mhnds` |
| Majed Al Muhandis | `mjd l mhnds` |
| Rashed Al Majed | `rshd l mjd` |
| Rashid Al Majid | `rshd l mjd` |
| Hussain Al Jassmi | `hsn l jsm` |
| Hussein Al Jasmi | `hsn l jsm` |

- لا نستخدم المفتاح القصير (أقل من 6 أحرف أو كلمة واحدة) لتجنب الأخطاء.
- إذا تطابق أكثر من فنان بالمفتاح، لا نختار تلقائياً؛ نرجع للمراجعة.
- المطابقة النهائية للأغنية لا تعتمد على الاسم فقط؛ نضيف العنوان والمدة والألبوم.

### قواعد التسجيل

| العنصر | النقاط |
|---|---:|
| تطابق العنوان العربي حرفياً | 40 |
| تطابق العنوان بعد التطبيع | 35 |
| تطابق العنوان اللاتيني | 30 |
| العنوان يحتوي/داخل | 20 |
| تطابق الفنان حرفياً | 25 |
| تطابق Alias | 20 |
| دويتو مذكور | 10 |
| فرق المدة ≤ 2s | 25 |
| فرق المدة ≤ 5s | 15 |
| فرق المدة ≤ 10s | 5 |
| Album/Year متطابق | 10 |
| Cover/فنان مختلف | رفض |

- **حد القبول:** 60+.
- **ثقة عالية:** 80+.
- **أقل من 60:** يذهب إلى `missing` أو مراجعة يدوية.
- لا تقبل نتيجة لمجرد تطابق العنوان؛ يجب وجود إشارة فنان أو مدة قريبة.

### Dedup

- نفس الأغنية قد تظهر: Single + Album + Live + Remix.
- احتفظ بها كـ `version` مختلفة.
- `canonical_key` يضم `duration_bucket` لتقليل الدمج الخاطئ.
- عند التصدير: احتفظ بالنسخة الاستوديو + المتزامنة إن وُجدت.

---

## 7.1) تقييم الجودة (Quality Gate)

راجع التقرير التفصيلي: `SOURCE_QUALITY.md`.

الخلاصة: fnanen وkalimataghani مصدران مفيدان، لكنهما ليسا «حقيقة» ولا يكفيان وحدهما. لذلك نضيف لكل نص:

- `quality_score` (0–1).
- `quality_flags` (JSON: one_line, short_lyrics, low_agreement, duplicate_title, no_metadata...).
- `source_agreement` (أعلى Jaccard مع مصدر آخر).
- `needs_review`.
- `manual_verified`.

ولا نختار `is_preferred` حسب المصدر فقط، بل حسب الجودة والاتفاق والمراجعة. الحالات منخفضة الجودة تدخل `v_review_queue` في `schema.sql`.

---

## 8) الكلمات المتزامنة (Synced)

### التخزين

```json
{
  "kind": "synced",
  "format": "lrc",
  "text": "[00:12.34] أول سطر\n[00:16.10] السطر الثاني",
  "line_count": 42,
  "has_synced": true,
  "has_word_sync": false
}
```

### التحقق

- كل سطر يبدأ بـ `[mm:ss.xx]` أو `[mm:ss.xxx]`.
- الترتيب الزمني تصاعدي.
- لا توجد أسطر فارغة في البداية.
- إذا كان الملف تالفاً: خزّنه كـ `raw_invalid` ولا تجعله preferred.

### عند عدم وجود تزامن

- `needs_alignment = true`.
- لاحقاً: WhisperX أو stable-ts لمزامنة النص مع الصوت.
- لا تؤجل جمع النص بسبب عدم وجود تزامن.

### ربطها بالواجهة (الصورة)

| العنصر في الواجهة | الحقل |
|---|---|
| العنوان | `title` / `title_ar` |
| المدة | `duration_label` |
| Synced | `has_synced` |
| Instrumental | `instrumental` |
| Album - Artist | `album` + `artist` |
| البحث | FTS5 على `title` + `artist` + `lyrics` |

---

## 9) شكل التصدير JSON

### ملف الفنان

```json
{
  "artist": {
    "slug": "fadhl-shaker",
    "name_ar": "فضل شاكر",
    "name_en": "Fadhl Shaker",
    "aliases": ["Fadel Chaker", "Fadel Shaker", "فضل شاكر"]
  },
  "generated_at": "2026-11-05T00:00:00Z",
  "stats": {
    "songs": 300,
    "with_lyrics": 240,
    "with_synced": 110,
    "instrumental": 12,
    "missing": 60
  },
  "songs": [
    {
      "id": "fadhl-shaker--fen-layalik--281",
      "title": "Fen Layalik",
      "title_ar": "فين لياليك",
      "artist": "Fadhl Shaker",
      "album": "Sah El Shok",
      "duration": 281,
      "duration_label": "4:41",
      "language": "ar",
      "instrumental": false,
      "has_synced": true,
      "has_word_sync": false,
      "lyrics_plain": "...",
      "lyrics_synced": "[00:12.34] ...\n[00:16.10] ...",
      "source": "LRCLIB",
      "source_id": 12345,
      "match_score": 0.96,
      "match_method": "title+artist+duration"
    }
  ],
  "missing": [
    {
      "title": "اسم الأغنية",
      "reason": "no_match"
    }
  ]
}
```

### ملف مجمّع

- `combined.json`: كل الفنانين في ملف واحد.
- `catalog.json`: فهرس خفيف للبحث (بدون نصوص كاملة) لتطبيق الكاريوكي.
- `lyrics/<song_id>.json`: نصوص منفصلة إذا احتاج التطبيق التحميل التدريجي.

---

## 10) الخطة الزمنية

### Phase 0 — الأساس (1–2 يوم)

- [x] إنشاء `artists.yaml` للقائمة النهائية (37 فناناً).
- [x] إنشاء Schema SQLite في `schema.sql`.
- [ ] تحويل ملفات fnanen/kalimataghani/fadel الحالية إلى القاعدة.
- [ ] إضافة `lyrics_synced` لملف فضل شاكر من LRCLIB.

### Phase 1 — Pilot (3–5 أيام)

- [ ] بناء `collect_catalog.py`.
- [ ] بناء `collect_lyrics.py`.
- [ ] بناء `match.py`.
- [ ] تشغيله على 3 فنانين: فضل شاكر، إليسا، كاظم الساهر.
- [ ] تقرير تغطية أولي.

### Phase 2 — التوسع (1–2 أسبوع)

- [ ] إضافة باقي Tier 1 (8–10 فنانين).
- [ ] مراجعة الأخطاء والتكرارات.
- [ ] تحسين مطابقة العربية والـ Aliases.
- [ ] إنشاء `missing.json` ومراجعة أهم النواقص يدوياً.

### Phase 3 — التوسع الكبير (2–3 أسابيع)

- [ ] إضافة Tier 2.
- [ ] قرار: LRCLIB dump أم API؟
- [ ] إضافة Tarab للأغاني العربية الناقصة.
- [ ] تحسين التغطية المتزامنة.
- [ ] تقرير جودة نهائي.

### Phase 4 — التطبيق (لاحقاً)

- [ ] واجهة بحث FTS5.
- [ ] عرض الكلمات المتزامنة.
- [ ] كاريوكي line-level.
- [ ] دعم word-level عند توفره.
- [ ] تصدير/مزامنة مع التطبيق.

---

## 11) معايير النجاح

| المقياس | الهدف المبدئي |
|---|---|
| تغطية الكلمات (أي نص) | ≥ 80% لـ Tier 1 |
| تغطية synced | ≥ 35–50% (واقعي للعربي) |
| دقة المطابقة (عينة 100 أغنية) | ≥ 95% |
| تكرارات غير مقصودة | < 5% |
| أغاني في `missing` | < 20% |
| زمن تحديث فنان واحد | < 10 دقائق (API) |

> الأرقام قابلة للتعديل بعد Pilot، خاصة أن تغطية LRCLIB للعربي أقل من الإنجليزي.

---

## 12) المخاطر والحلول

| الخطر | الحل |
|---|---|
| LRCLIB تغطية عربية محدودة | إضافة fnanen/kalimataghani وTarab |
| LRCLIB أخطاء/تكرارات | Match score + مراجعة عينة + `source_id` |
| fnanen/kalimataghani تتغير | Cache + retries + مراقبة الـ parser |
| أسماء فنانين متعددة | `artist_aliases` + تطبيع |
| نسخ Live/Remix | `version` + `canonical_key` |
| الحجم الكبير | API أولاً، ثم dump عند الحاجة |
| حقوق النشر | استخدام شخصي، عدم إعادة النشر، حفظ المصدر |
| LyricFind 403 | لا نتجاوزه؛ نستخدم الكتالوج فقط |

---

## 13) قرارات مطلوبة منك

1. **قائمة الفنانين النهائية للـ Tier 1**: هل نضيف/نحذف أحداً؟
2. **التشكيل**: هل نحتفظ به كما هو (kalimataghani) أم ننتج نسخة موحّدة بدون تشكيل للبحث؟
3. **النسخ**: هل نريد كل النسخ (Live/Remix) أم نسخة استوديو واحدة فقط؟
4. **الترجمات**: هل نضيفها لاحقاً لتعلم العربية؟
5. **مساحة التخزين**: هل عندك مساحة لـ LRCLIB dump (~46 GiB مضغوط) أم نبدأ API فقط؟
6. **الترتيب**: هل نبدأ بفضل شاكر وإليسا (لوجود بيانات) أم بكاظم الساهر؟

---

## 14) الخطوات التالية الفورية

1. اعتماد `artists.yaml` للـ Tier 1.
2. إنشاء قاعدة SQLite بالـ Schema أعلاه.
3. تحويل الملفات الحالية إلى القاعدة (migration).
4. إعادة جلب LRCLIB لملف فضل شاكر مع `syncedLyrics`.
5. تشغيل Pilot على 3 فنانين.
6. إنتاج `report.csv` و`missing.json`.
7. اتخاذ قرار LRCLIB dump بناءً على نتائج الـ Pilot.

---

## 15) ملاحظة أخيرة

الهدف ليس «جمع أكبر عدد» فقط، بل **جمع أكبر عدد قابل للاستخدام**.  
أغنية بنص كامل غير متزامن أفضل من لا شيء، لكن أغنية بنص متزامن أفضل لتطبيق الكاريوكي.  
لذلك سنقيس دائماً:

- كم أغنية عندها نص؟
- كم منها متزامن؟
- كم منها متزامن على مستوى الكلمة؟
- كم منها يحتاج مراجعة؟

وهذه المقاييس هي التي ستوجه التوسع، وليس عدد الملفات فقط.
