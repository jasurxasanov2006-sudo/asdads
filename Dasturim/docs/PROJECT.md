# DataFlow AI — loyiha holati

## Maqsad

Windows kompyuterida lokal ishlaydigan analitika ish maydoni: CSV/Excel yuklash, ma'lumotni tekshirish va tozalash, SQL, grafiklar, notebook hamda AI yordamchisi.

## Tuzilishi

- `backend/`: FastAPI serveri va tahlil modullari.
- `frontend/`: bitta HTML sahifa va lokal JavaScript fayllari; tashqi CDN talab qilinmaydi.
- `workspace/`: jadval versiyalari, daftar va dashboard saqlanadi; maxfiy/foydalanuvchi ma'lumotlari, Git'ga kiritilmaydi.
- `test-data/`: sinov uchun kichik CSV fayllar.
- `docs/`: loyiha qarorlari va keyingi vazifalar.

## BOSQICH 0

- Backend importi va kompilyatsiyasi tekshirilgan.
- Dashboard API frontend bilan ulangan; saqlash, SQL bajarish va o'chirish yo'llari bor.
- HTML hisobot, Excel, g'ayritabiiy qiymatlar, URL/DB import va zaxira uchun frontend bo'limi qo'shilgan.
- Pytest to'plami, o'rnatish ro'yxati, Windows ishga tushirish fayli va Git ignore qoidalari qo'shilgan.
- Tekshiruv: `30 passed`; Python compile, JavaScript sintaksisi va `pip check` muvaffaqiyatli.
- Ilova `127.0.0.1:8001` da ishga tushirilib, sahifa va skript endpointlari tekshirildi; brauzerda 8 ta menyu bo'limi ochildi, JavaScript runtime xatosi chiqmadi.
- Keyingi qo'lda tekshiruvda 8000-port bo'sh chiqdi; `start.bat` bilan server ochilib, `/health` HTTP 200 qaytardi.
- Brauzerda 8000-portdagi Dashboard paneli 10 qatorli SQL natijasini ko'rsatdi; "Hisobot va import" bo'limi va 5 ta raqamli ustun ochildi. Brauzerda JavaScript xatosi chiqmadi.
- Foydalanuvchi `.\backend\venv\Scripts\python.exe -m pytest -q` buyrug'ini yana bajardi: `30 passed`.
- Tashqi URL/ma'lumotlar bazasi ulanishi va zaxira yaratish haqiqiy manbalarga murojaat yoki diskka arxiv yozishni talab qiladi; ular bu tekshiruvda bajarilmadi.

## BOSQICH 1

- Tozalash amallari kengaydi: matnni trim/kichik-katta harf/bo'shliqlar bilan normallashtirish, raqam va sanaga o'tkazish (ming/o'nlik ajratgichi va sana formati bilan), ISO sana, ustunni qayta nomlash/o'chirish/bo'lish/birlashtirish, ro'yxat bilan almashtirish va bo'shni "noma'lum" bilan to'ldirish.
- Retseptlar `workspace/recipes/*.json` ichida saqlanadi, ro'yxat ko'rinadi va boshqa jadvalga qo'llanadi. Ustun mos kelmasa, qadam raqami bilan xabar beradi.
- Tozalash oldidan `dry_run` bilan oldingi/keyingi ko'rinish hamda qator/muammo hisoblagichlari chiqadi; qo'llash undo-historiyaga yoziladi.
- Deyarli takror qatorlar tanlangan ustunlarda harf registri va bo'shliqlarni normallashtirib aniqlanadi. Natijada har guruhdan 10 tagacha namuna qatori ko'rsatiladi; haqiqiy o'chirishda guruhning hamma takrorlari ko'rib chiqiladi.
- Test natijasi: `48 passed`; compileall, JavaScript sintaksisi, `pip check` muvaffaqiyatli.
- `127.0.0.1:8000` serverida tozalash oynasi, dry-run, retsept qadamini qo'shish va katta takror guruhlarining qisqa ko'rinishi brauzerda tekshirildi; sahifa JavaScript xatosi chiqmadi.

## BOSQICH 2

- Ko'p jadval bo'yicha AI SQL, tushuntirish rejimi, tozalash tavsiyalari va FARAZ-insightlar bajarilgan.
- AI provider, maxfiylik, tarix va so'rov limiti sozlamalari; tushunarli xato/kvota xabarlari va fallback mavjud.
- Tekshiruv: `56 passed`; brauzerda sozlamalarni saqlash tekshirilgan.

## BOSQICH 3

- Jadval versiyalari DuckDB orqali ZSTD siqilgan Parquet formatida saqlanadi; eski `workspace/<jadval>/vN.csv` fayllari dastur ishga tushganda `projects/default/tables` ostiga xavfsiz ko'chirilib, Parquet'ga aylantiriladi. CSV faqat eksport formati sifatida qoladi.
- Loyiha yaratish/almashtirish API va UI'da mavjud; jadvallar, dashboard panellari va Python notebook kataklari loyiha bo'yicha ajratilgan.
- Excel importida varaq(lar)ni tanlash yoki hammasini import qilish mumkin. Yuklash progressi, 1 GB hajm chegarasi, DuckDB Parquet sahifalashi va ustun bo'yicha saralash qo'shilgan.
- 1 000 000 qatorli, 107.6 MiB CSV sinovida ochish 3.799 s, 100 qatorli sahifa 0.196 s, `COUNT(*)` SQL 3.342 s, statistika 3.516 s bo'ldi (joriy ishlab chiqish mashinasida; har biri 10 s dan kam).
- Tekshiruv: migratsiya, loyiha ajratilishi, Excel varaqlari va sahifalash testlari; umumiy natija `61 passed`, Python compileall va frontend JavaScript sintaksisi muvaffaqiyatli.

## BOSQICH 4

- Pivot jadval qator/ustun/qiymat va yig'indi/soni/o'rtacha/min/max hisoblashlari, jami qator/ustun bilan qo'shildi.
- Dashboard panellari SQL asosida saqlanadi; KPI kartochkasi, grid kengligi, tartibini o'zgartirish, tahrirlash va HTML eksport mavjud.
- Qiymat tanlash va sana oralig'i filtrlari loyiha ichida saqlanadi hamda barcha mos jadvallarni ishlatadigan panellarga tatbiq qilinadi.
- Grafiklarda o'ng Y o'qi, kun/oy/yil bo'yicha sana guruhlash, nuqtalar bo'yicha tooltip, kattalashtirish/kichraytirish va surib ko'rish qo'shildi. SVG grafiklar lokal chiziladi, internet yoki CDN kerak emas.
- Dashboard filtrlarini saqlab qayta ochish, panel tahriri/tartibi/HTML eksporti, pivot jami/filtrlari testlarda tekshirildi; umumiy natija `66 passed`, Python compileall va frontend JavaScript sintaksisi muvaffaqiyatli.

## BOSQICH 6

- Python notebook bitta loyiha bo'yicha uzoq ishlaydigan kernel ishlatadi; kataklar orasida o'zgaruvchilar saqlanadi, qayta boshlash va bajarishni to'xtatish tugmalari qo'shildi.
- Kernel bajarish vaqtini 30 soniyada to'xtatadi. Windows Job Object process memory limitini 1 GiB, faol process limitini 2 ta qilib belgilaydi; Python AST siyosati fayl, tarmoq, process va introspection amallarini cheklaydi. Notebook API localhost guard bilan himoyalangan.
- Python va Markdown kataklari, kataklarni yuqori/pastga ko'chirish va nusxalash, `.py`/`.ipynb` import-eksport qo'shildi; eski katak JSON formati kod kataklari sifatida o'qiladi.
- `matplotlib` va `scikit-learn` ixtiyoriy: muhitda o'rnatilgan bo'lsa import qilish mumkin, matplotlib grafiklari PNG shaklida katak natijasida chiqadi.
- Stage 6 uchun persistent state, restart, timeout, fayl amallarini taqiqlash, notebook API va format round-trip testlari qo'shildi.
- Tekshiruv: `71 passed`; Python compileall va notebook JavaScript sintaksisi muvaffaqiyatli.

## BOSQICH 7

- Ko'p varaqli Excel hisobotida ma'lumot, umumiy ko'rsatkichlar, statistika, muammolar va raqamli ustunlar diagrammasi bor. Openpyxl hamda Pillow logotipni (PNG/JPEG/WebP) xlsx'ga joylaydi.
- HTML hisobotda sarlavha/logotip sozlamasi va brauzer chop etishi mavjud; PDF uchun chop etish oynasi ochiladi.
- Marketing va moliya yo'nalishidagi 7 ta shablon faol jadval ustunlarini tanlab, xavfsiz SELECT natijasi hamda SQL/Python namunasini ko'rsatadi. Natijalar tekshiruv indikatorlari ekani va audit o'rnini bosmasligi ochiq aytiladi.
- Loyiha bo'yicha kunlik hisobot yangilash va HTML/Excel avtomatik saqlash sozlamalari, qo'lda yangilash va saqlangan fayllarni yuklash qo'shildi.
- Stage 7 uchun xlsx varaqlari/grafik/logotip, chop etish, sozlamalar, shablonlar, ustun validatsiyasi va rejalashtirilgan saqlash testlari qo'shildi.
- Tekshiruv: `76 passed`; Python compileall, frontend JavaScript sintaksisi va `pip check` muvaffaqiyatli.

## BOSQICH 8

- Login/session, PBKDF2-SHA256 parol xeshi, CSRF, localhost bootstrap yoki server bootstrap tokeni, IP rate-limit, rol nazorati, foydalanuvchi boshqaruvi va audit jurnali qo'shildi. Kamida bitta faol administratorni saqlash tekshiruv bilan himoyalangan.
- Workspace'lar foydalanuvchi ID bo'yicha ajratildi; mavjud local workspace birinchi admin'ga biriktiriladi. Loyihalar, faollashtirilgan loyiha va notebook state request context'da foydalanuvchi bo'yicha tanlanadi. Kunlik hisobot scheduler barcha faol foydalanuvchilar/workspace'larni navbatma-navbat ko'radi.
- Interfeysda login/ilk setup, administratorning user/audit oynasi, til tanlagich (uz/ru/en), to'rt qadamli onboarding va yordam/FAQ qo'shildi.
- Server uchun Docker Compose + Caddy HTTPS reverse proxy, env sozlamalari, qat'iy CORS, persistent volume va bir worker rate-limit sozlamasi berildi. Python hamda SQL Docker worker konteynerida (`network=none`, non-root, read-only filesystem, 1 GiB/1 CPU/32 process/30s) ishlaydi; backend-controller bearer token bilan bog'lanadi, hostga app/sandbox porti ochilmaydi.
- Windows desktop uchun PyInstaller one-file paket va Inno Setup skript/build fayllari qo'shildi; data va AI settings `%APPDATA%` ostida qoladi. Mahalliy notebook localhost'da saqlanadi, remote server esa Docker sandbox rejimini majburiy ishlatadi.
- Stage 8 uchun auth/bootstrap/CSRF/rol/workspace ajratilishi, SQL/Python sandbox routing testlari qo'shildi. Docker Engine/Caddy sertifikat va PyInstaller/Inno Setup yakuniy paket smoke-testi target platforma talab qilgani uchun lokal pytest bilan tekshirilmaydi.
