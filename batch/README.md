# Batch Job — تنظيف وتصفية كلمات الأغاني

هذا Job يعمل لمدة محددة (افتراضياً 120 دقيقة)، ينظّف البيانات الحالية، يجلب أغاني إضافية من iTunes وLRCLIB، يحسب جودة كل نص، ثم ينتج حزمة مراجعة.

## ماذا يفعل؟

1. **يستورد البيانات الموجودة:**
   - `fnanen` (إليسا، فضل شاكر)
   - `kalimataghani` (إليسا، فضل شاكر)
   - `fadel_chaker_lyrics.json` (LyricFind + LRCLIB)

   ثم يبدأ بإليسا وفضل شاكر (لأن لديهما بيانات أولية)، وبعدها بقية Tier 1 حسب `artists.yaml`.

2. **ينظّف النصوص:**
   - إزالة HTML والرموز الخفية.
   - توحيد المسافات ونهايات الأسطر.
   - اكتشاف: سطر واحد، نص قصير، حروف لاتينية، تشكيل، عناوين مكررة.

3. **يجلب أغاني جديدة:**
   - iTunes Search API → قائمة أغاني الفنان + المدة + الألبوم.
   - LRCLIB API → كلمات Plain + Synced.

4. **يحسب الجودة:**
   - `quality_score` لكل نص.
   - `quality_flags` مثل `one_line`, `short_lyrics`, `low_agreement`, `snippet_mismatch`.
   - `needs_review`.

5. **ينتج حزمة مراجعة:**
   - `review/candidates.csv` — كل النصوص مع درجة الجودة.
   - `review/review_queue.csv` — المشكوك فيها فقط.
   - `review/songs.csv` — ملخص كل أغنية.
   - `review/artists.csv` — إحصاءات الفنانين.
   - `review/summary.md` — ملخص.

## تشغيل على VM

```bash
# 1. تجهيز البيئة
python3 -m venv .venv
source .venv/bin/activate
pip install -r batch/requirements.txt

# 2. اختبار سريع (5 دقائق)
python -m batch.job --config batch/config.yaml --minutes 5 --only elissa,fadl-shaker

# 3. التشغيل الكامل (ساعتان)
python -m batch.job --config batch/config.yaml --minutes 120

# 4. متابعة السجل
tail -f batch/run.log
```

### خيارات مفيدة

| الخيار | المعنى |
|---|---|
| `--minutes 120` | ميزانية الوقت بالدقائق |
| `--only elissa,fadl-shaker` | فنانين محددين فقط |
| `--skip-fetch` | تنظيف البيانات الموجودة فقط، بدون جلب جديد |
| `--limit-songs 20` | حد أغاني لكل فنان (للاختبار) |
| `--db data/test.db` | قاعدة بيانات منفصلة |
| `--force` | إعادة معالجة الفنانين المكتملين |

## الاستئناف

- الـ Job يحفظ التقدم في SQLite وفي `batch/run.log`.
- إذا توقف أو انتهى الوقت، أعد تشغيل نفس الأمر؛ سيتخطى الفنانين المكتملين ويكمل الباقي.
- إذا توقف في منتصف فنان، سيعيد ذلك الفنان من البداية (مع الاستفادة من الـ cache).
- `Ctrl+C` يحاول إنهاء الخطوة الحالية وحفظ النتائج.
- `--force` لإعادة معالجة الكل من جديد.

## ماذا تراجع؟

افتح:

```text
review/review_queue.csv
```

أو `review/candidates.csv` في Excel/LibreOffice.

- رتّب حسب `quality_score` تصاعدياً (الأسوأ أولاً).
- راجع `flags`.
- املأ عمود `decision`:

| القرار | المعنى |
|---|---|
| `keep` | النص صحيح، اعتمده |
| `reject` | النص خاطئ/غير مرغوب |
| `edit` | يحتاج تعديل يدوي |
| `merge` | يحتاج دمج مع نسخة أخرى |

- اكتب ملاحظات في `notes`.
- أعد تشغيل:

```bash
python -m batch.apply_review --csv review/candidates.csv
```

## الأسماء البديلة

- كل فنان له `aliases` في `artists.yaml`.
- عند المطابقة نستخدم أيضاً `latin_key` الذي يوحّد:
  - `Fadel / Fadhl / Fadhel`
  - `Shaker / Chaker / Shakir`
  - `Majid / Majed`
  - `Rashed / Rashid`
  - `Hussain / Hussein / Husain`
- هذا يقلل فقدان الأغاني بسبب اختلاف كتابة الاسم.

## ملاحظات

- الجلب من iTunes محدود بـ 200 أغنية لكل فنان. للفنانين الأكثر من ذلك، نحتاج لاحقاً إلى جلب الألبومات ثم أغانيها.
- LRCLIB قد يطابق الأغنية الخطأ؛ لذلك يوجد `snippet_mismatch` و`low_agreement`.
- لا نحذف أي نص؛ نخزّن كل النسخ ونختار `is_preferred` حسب الجودة.
- الكلمات المحمية بحقوق نشر؛ هذا للاستخدام الشخصي فقط.
- لا نحاول تجاوز حجب LyricFind.

## المتطلبات

- Python 3.10+
- اتصال إنترنت
- مساحة قرص: 1–2 GB للـ cache وSQLite (قد تزيد)
