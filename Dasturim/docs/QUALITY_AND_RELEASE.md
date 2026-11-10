# BOSQICH 9 — Sifat va ishga tushirish

## Tekshiruv natijalari

Tekshiruvlar Windows ishlab chiqish muhitida 2026-11-07 kuni bajarildi:

- Testlar: **95 passed**.
- Backend line coverage: **75%** (`coverage run --source=backend -m pytest -q`; `coverage report --include="backend/*.py"`).
- 1,000,000 qatorli, 106.1 MiB CSV: yuklash/ochish **6.773 s**, 100 qatorli sahifa **0.091 s**, `COUNT(*)` SQL **4.893 s**, statistika **5.292 s**. Har biri 10 soniyalik mezondan past.
- Frontend JS, shu jumladan `index.html` ichidagi inline script, sintaksis tekshiruvi; Python compileall va desktop local smoke-test.

Benchmarkni qaytarish:

```powershell
.\backend\venv\Scripts\python.exe .\tools\benchmark_stage9.py
```

Boshqa qator miqdori uchun `DATAFLOW_BENCHMARK_ROWS` muhit o'zgaruvchisini belgilang. Benchmark 10 soniyadan oshgan amalda xato bilan tugaydi. Natijalar apparat, disk, Python va DuckDB versiyasiga bog'liq; production apparatida ham qaytarish kerak.

## Xavfsizlik checklisti

| Tekshiruv | Holat | Qayd |
|---|---|---|
| SQL injection / ko'p buyruq | Avtomatlashtirilgan tekshiruv o'tdi | Faqat bitta `SELECT`/`WITH` qabul qilinadi; `COPY`, fayl o'qish va o'zgartiruvchi buyruqlar rad etiladi. Bu mustaqil penetration-test o'rnini bosmaydi. |
| Fayl yo'li / path traversal | Avtomatlashtirilgan tekshiruv o'tdi | Saqlangan hisobot yo'li workspace ichida tekshiriladi; yuklangan nomlar temp fayl suffixi va xavfsiz response headerga aylanadi. |
| CSV/Excel formula injection | Avtomatlashtirilgan tekshiruv o'tdi | CSV, SQL natijasi CSV va XLSX eksportida formula sifatida talqin qilinishi mumkin bo'lgan matnlar neytrallanadi; oddiy manfiy sonlar o'zgarishsiz qoladi. |
| HTML/XSS | Fokusli test o'tdi | Hisobot ustun sarlavhalari HTML sifatida chiqarilishidan oldin escape qilinadi; frontend dinamik qiymatlarida mavjud `esc()` ishlatiladi. Yangi UI o'zgarishlarida shu qoidani saqlang. |
| Yuklash hajmi | Avtomatlashtirilgan chegaraviy test o'tdi | CSV/XLSX yuklash 1 GiB bilan cheklangan; URL importi 20 MiB bilan cheklangan. Test hajm konstantasini kichraytirib limitni katta fayl yaratmasdan tekshiradi. |
| Xato jurnali | Tekshirildi | Backend loglari stdout/stderr oqimiga yoziladi; Docker'da `docker compose logs backend sandbox-controller proxy` bilan ko'riladi. Scheduler istisnolari stack trace bilan yoziladi. Xom parol, API kaliti yoki fayl mazmunini loglamang. |
| Server sandbox / HTTPS | Muhitda bajarilmadi | Docker mavjud emas edi; serverga joylashdan oldin Compose, TLS, sandbox va worker limitlarini target Linux hostda tekshiring. |

## Foydalanuvchi sinovi

Analitiklar bilan 5–10 ta sinovni bu ish muhiti ichida ishonchli tashkil qilish yoki haqiqiy mijoz fayllarini olish imkoni yo'q. Natija, rozilik yoki pul to'lash istagi haqida ma'lumot to'qib chiqarilmadi; **bu ishga tushirish mezoni ochiq qoladi**.

Haqiqiy fayl bilan ishlashdan oldin ishtirokchining roziligini oling; shaxsiy/maxfiy ustunlarni olib tashlang yoki sintetik nusxa ishlating. Fikrlarni [analyst_feedback_template.csv](../test-data/analyst_feedback_template.csv) fayliga kiriting. Har bir kishi uchun quyidagilar qayd etilsin:

- vazifani bajara oldimi, avvalgi va DataFlow AI bilan ketgan vaqt;
- vaqt tejash haqidagi bevosita javobi;
- xato, tushunarsiz joy va taklif;
- ikkinchi haftada qaytib foydalangan-foydalanmagani;
- pul to'lashga tayyorligi va aytgan narxi (bu savolga javob ixtiyoriy).

## Go / no-go mezonlari

Hozircha **NO-GO**: kod va lokal samaradorlik mezonlari o'tdi, lekin quyidagi mahsulot mezonlari haqiqiy foydalanuvchi va AI natijalari bilan hali tasdiqlanmagan:

1. 10 analitikdan kamida 5 nafari “vaqtimni tejaydi” deb javob bersin.
2. 10 analitikdan kamida 3 nafari pul to'lashga tayyorligini bildirsin.
3. AI javoblarining kamida 90% i oldindan yozilgan ground-truth javoblar bilan to'g'ri chiqsin.
4. Birinchi haftada sinagan 10 kishidan kamida 3 nafari ikkinchi haftada qaytsin.

`test-data/ai_questions.json` faylida 16 ta savol bor, ammo fixture sxemasi, to'g'ri SQL, kutilgan natija va baholash ma'lumotlari yo'q. Shuning uchun hozircha AI aniqligining haqiqiy foizi o'lchanmagan. Provider API kaliti va ground-truth javoblari bor baholash to'plami tayyorlangach o'lchanadi. **Mahsulot mezonlari bajarilib, server deployment maqsadli hostda muvaffaqiyatli tekshirilgandan keyingina GO beriladi.**
