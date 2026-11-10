# Qarorlar

- Dastur serveri faqat `127.0.0.1` da tinglaydi; `0.0.0.0` ishlatilmaydi.
- Frontend kutubxonalari lokal JavaScript fayllaridan yuklanadi; CDN qo'shilmaydi.
- Jadval qiymatlari xom ko'rinishda saqlanadi, SQL/statistika uchun `typed_frame` turini aniqlaydi.
- Jadval versiyalari Parquet/ZSTD fayllarida saqlanadi; DuckDB fayllarni o'qiydi va sahifalangan natijalarni beradi.
- Workspace bir nechta loyihaga ajratiladi; jadval, dashboard va notebook ma'lumotlari aktiv loyiha ichida saqlanadi.
- Eski `workspace/<jadval>/vN.csv` versiyalari `projects/default/tables` ichiga ko'chirilib, Parquet'ga aylantiriladi; CSV eksport uchun qoladi.
- SQL so'rovlari bajarilishidan avval `check_sql` tekshiruvidan o'tadi.
- AI savol-javob namuna qatorlarini yuborish sozlamasini `.env` dan modelga murojaat qilishdan oldin o'qiydi; `AI_SEND_SAMPLE=false` bo'lsa namuna yuborilmaydi.
- Dashboard va ishchi ma'lumotlar lokal `workspace` ichida qoladi; `.env`, `workspace` va zaxiralar Git'dan chetda.
- Mavjud per-jadval dashboard API saqlanib, yangi frontend kutayotgan umumiy dashboard API qo'shildi.
- Database import paroli forma yuborilgandan so'ng sahifada tozalanadi; profilga saqlanmaydi.
- Retseptlar har biri UUID nomli JSON fayl sifatida `workspace/recipes` ichida saqlanadi; qo'llashda har bir qadam joriy jadval ustunlariga qayta tekshiriladi.
- Deyarli takror qatorlar faqat tanlangan ustunlar bo'yicha trim, ichki bo'shliqni qisqartirish va harf registrini tenglashtirish orqali topiladi; o'xshashlik foizi bilan taxmin qilinmaydi.
- Dry-run faqat hisoblangan natija va dastlabki 10 qatorni ko'rsatadi, versiya yoki CSV faylga yozmaydi.
