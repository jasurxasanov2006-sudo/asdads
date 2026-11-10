# DataFlow AI

DataFlow AI — analitiklar uchun Windows kompyuterida lokal ishlaydigan ma'lumot tahlili dasturi.

## Birinchi o'rnatish

1. Python 3.13 o'rnatilganini tekshiring.
2. `backend` papkasida terminal oching va virtual muhit yarating:

   ```powershell
   if (-not (Test-Path .\venv)) { py -3.13 -m venv venv }
   .\venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt --default-timeout=100 --retries 10
   ```

3. AI ishlatmoqchi bo'lsangiz, `backend\.env` yarating va `GEMINI_API_KEY` ni kiriting. Kalitni boshqalarga yubormang yoki repozitoriyga qo'shmang. AI kalitisiz yuklash, tozalash, SQL va grafiklar ishlaydi.

## Ishga tushirish

- Loyiha papkasidagi `start.bat` faylini ikki marta bosing. U serverni faqat `127.0.0.1` manzilida ishga tushiradi va brauzerni ochadi.
- Yoki `backend` ichida `venv\Scripts\activate` va `uvicorn main:app --reload` buyrug'ini bajaring.
- Manzil: <http://127.0.0.1:8000/>

Server ishlamay qolsa, terminaldagi xabarni tekshiring. 8000-port band bo'lsa, avval DataFlow AI'ning eski oynasini yoping; boshqa dastur jarayonini majburan to'xtatmang.

## Testlar

Loyiha ildizidagi terminalda:

```powershell
.\backend\venv\Scripts\python.exe -m pytest
```

Namuna fayllar `test-data` papkasida. Ishchi jadval va maxfiy sozlamalar Git'ga kiritilmaydi.

Qamrov va BOSQICH 9 benchmarki:

```powershell
.\backend\venv\Scripts\python.exe -m coverage run --source=backend -m pytest -q
.\backend\venv\Scripts\python.exe -m coverage report --include="backend/*.py"
.\backend\venv\Scripts\python.exe .\tools\benchmark_stage9.py
```

Ishga tushirish checklisti va analitiklar uchun fikr-mulohaza shakli: [docs/QUALITY_AND_RELEASE.md](docs/QUALITY_AND_RELEASE.md).

## Tozalash retseptlari

1. Jadvalni tanlab, **Tozalash** bo'limida kerakli amal va ustunni belgilang.
2. **Oldin/keyin ko'rish** o'zgarishni saqlamasdan natijani ko'rsatadi.
3. **Retseptga qadam qo'shish** bilan bir nechta amalni ketma-ket yig'ing va nom berib saqlang.
4. Saqlangan retseptni boshqa jadvalga **Retseptni ko'rish** bilan tekshirib, keyin qo'llang. Ustun nomi mos kelmasa, amal bajarilmay xato ko'rsatiladi.
5. Qo'llangan o'zgarishni **Bekor qilish** tugmasi bilan qaytarish mumkin.

## Loyihalar va katta fayllar

- **Loyiha** tanlagichidan loyihani almashtiring yoki yangisini yarating. Har bir loyiha o'z jadvallari, dashboard panellari va Python notebook kataklarini saqlaydi.
- CSV/Excel fayllari 1 GB gacha yuklanadi; yuklash jarayoni progress bilan ko'rsatiladi. Excel importida kerakli varaqlarni yoki barcha varaqlarni tanlash mumkin.
- Jadval qatorlarini sahifa-sahifa ko'ring; ustun sarlavhasini bosib saralang. SQL DuckDB'da bajariladi; statistika butun jadval bo'yicha hisoblanadi.
- Asosiy saqlash formati Parquet (`workspace\projects\<loyiha>\tables`); eski bir-loyihali workspace birinchi ishga tushishda avtomatik ko'chiriladi. CSV faqat eksport uchun ishlatiladi.

## Pivot va dashboard

- **Grafiklar** bo'limida qator, ustun, qiymat va hisoblash usulini tanlab pivot yarating; yig'indi qator/ustun ham ko'rsatiladi.
- SQL natijasini dashboardga qo'shib KPI yoki grafik/jadval panelini yarating. Panelni tahrirlash, kengligini o'zgartirish, yuqoriga/pastga ko'chirish va o'chirish mumkin.
- Dashboarddagi global qiymat va sana filtrlari tanlangach **Filtrlarni qo'llash va saqlash** tugmasini bosing. Filtr holati loyiha bilan saqlanadi va mos panellarga qayta ochilganda ham qo'llanadi.
- **HTML eksport** joriy filtrlar bilan panellarni mustaqil HTML fayliga chiqaradi.
- Grafiklarda zoom/pan, ikki Y o'qi va sana bo'yicha kun/oy/yil guruhlash bor. SVG grafiklar lokal chiziladi, internet talab qilinmaydi.

## Python notebook

- Mahalliy Windows rejimida Python kataklari bitta doimiy kernel jarayonida ishlaydi; o'zgaruvchilar kataklar orasida saqlanadi. **Qayta boshlash** o'zgaruvchilarni tozalaydi, **To'xtatish** joriy bajarishni uzadi.
- Kataklarni Markdown yoki Python sifatida qo'shing, ko'chiring, nusxalang va o'chiring. Daftarni `.py` yoki `.ipynb` formatida import/eksport qilish mumkin.
- Mahalliy kernel 30 soniya, 1 GiB xotira va Windows'da Job Object process limitlari bilan cheklangan. Bu localhost uchun himoya bo'lib, serverga ochiq tarmoqdan foydalanish uchun sandbox o'rnini bosmaydi.
- Matplotlib va scikit-learn o'rnatilgan bo'lsa, qo'shimcha o'rnatmasdan foydalanish mumkin; matplotlib grafiklari katak natijasida ko'rsatiladi.

## Hisobotlar va tahlil shablonlari

- **Hisobot va import** bo'limida HTML hisobotini, chop etish oynasi orqali PDF'ni yoki `Ma'lumot`, `Umumiy`, `Statistika`, `Muammolar`, `Grafiklar` varaqlaridan iborat Excel faylini oling.
- Sarlavha va PNG/JPEG/WebP logotipni sozlang. Kunlik yangilash va saqlangan HTML/Excel nusxalarini yoqish mumkin; buning uchun DataFlow AI serveri ishlab turgan bo'lishi kerak. **Hisobotlarni hozir yangilash** qo'lda saqlaydi.
- Shablonlar galereyasida Marketing (RFM, kohorta, voronka, kampaniya) va Moliya (debet/kredit mosligi, takroriy tranzaksiya, g'alati summa) tahlillari bor. Faol jadval ustunlarini moslang; har bir shablon natijasi SQL va Python namunalarini ko'rsatadi.
- Shablon natijalari tekshirish uchun ko'rsatkich/tavsiya xolos; ular hukm emas va audit o'rnini bosmaydi.
- Sozlamalar va avtomatik saqlangan fayllar loyiha ichidagi `reports` papkasida turadi.

## BOSQICH 8: mahsulot rejimi, foydalanuvchilar va deployment

### Lokal desktop

- Birinchi kirishda localhost orqali admin login/parolini yarating (kamida 12 belgi). Parollar PBKDF2-SHA256 bilan xeshlanadi; ochiq parol saqlanmaydi.
- Admin foydalanuvchilar va rollarni (`admin`, `analyst`, `viewer`) boshqaradi. Har hisob uchun alohida workspace; birinchi admin mavjud lokal workspace egasi bo'ladi.
- Session 12 soat amal qiladi, CSRF tokeni talab qilinadi, so'rovlar va kirish hodisalari audit jurnaliga yoziladi. Login urinishlari IP bo'yicha cheklanadi.
- O'zbekcha, ruscha va inglizcha til tanlagichi, 4 qadamli tanishtirish hamda Yordam/FAQ mavjud.
- Bitta faylli Windows ilovasi: avval `build-desktop.bat`, so'ng Inno Setup 6 o'rnatilgan bo'lsa `build-installer.bat`. Natija `dist\DataFlowAI-Setup.exe`. Ilova ma'lumotlari `%APPDATA%\DataFlowAI` ichida qoladi.

### Linux server (Docker Compose)

Server rejimida ilovani internetga bevosita Uvicorn orqali emas, faqat Caddy HTTPS reverse-proxy orqali chiqaring. Backend porti hostga publish qilinmaydi; Compose `80/443` portlarini ochadi. Docker Engine va Compose v2 hamda domeningizga yo'naltirilgan DNS kerak.

1. Repository ildizida `.env.example` faylidan `.env` nusxa oling. `DOMAIN`ni o'z domeningizga, `DATAFLOW_BOOTSTRAP_TOKEN` va `DATAFLOW_SANDBOX_TOKEN`ni bir-biridan farqli, noyob tasodifiy qiymatlarga almashtiring. Har bir token uchun buyruqni alohida bajaring:

   ```powershell
   .\backend\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   AI ishlatmoqchi bo'lsangiz, API kalitlarini ham `.env`ga kiriting. `.env` maxfiy fayl; hech qachon repository yoki loglarga qo'shmang.

2. Docker Compose'ni ishga tushiring:

   ```powershell
   docker compose --env-file .env -f deployment\docker-compose.yml up --build -d
   ```

   Birinchi ishga tushishda Python sandbox image'i quriladi va ko'p vaqt olishi mumkin. Holat/loglar:

   ```powershell
   docker compose --env-file .env -f deployment\docker-compose.yml ps
   docker compose --env-file .env -f deployment\docker-compose.yml logs -f backend sandbox-controller proxy
   ```

3. `https://<DOMAIN>` manzilida birinchi administratorni yarating. `.env`dagi bootstrap token faqat shu birinchi sozlash uchun kerak; tokenni maxfiy tuting.

- Caddy sertifikatni avtomatik boshqaradi; secure session cookie, tor CORS origin, auth, role enforcement, CSRF va IP rate-limit yoqilgan.
- `backend` bir worker bilan ishlaydi (in-memory rate-limit barcha so'rovlar uchun umumiy qolishi uchun). Persistent data `/data` Docker volume'da, auth SQLite DB va har foydalanuvchining loyiha papkalari shu yerda saqlanadi.
- Python **va SQL** alohida, har ishga tushishda yo'q qilinadigan rootless Docker worker konteynerida bajariladi: tarmoq yo'q, host mount/socket/secrets yo'q, non-root UID, read-only filesystem, 1 GiB RAM, 1 CPU, 32 process, 30 soniya; ko'pi bilan ikki ish bir vaqtda bajariladi. Notebook oldingi kataklarni qayta ijro qilib o'zgaruvchi holatini tiklaydi.
- Sandbox controller faqat Docker bridge tarmog'ida va alohida bearer token talab qiladi; token worker'ga berilmaydi. Worker `network=none` bilan ishga tushadi. Rootless Docker daemon uchun Compose'da `privileged` yoqilgan; daemon rootless rejimda ishlaydi, porti hostga publish qilinmaydi. Serverni ishga tushiruvchi operator bu talab va host Docker xavfsizlik modelini tekshirishi kerak.
- Compose resurs cheklovlari jami taxminan 7 GiB gacha xotira talab qilishi mumkin; Linux host uchun kamida 8 GiB tavsiya qilinadi. Rootless DIND image pull/build jarayoniga internet chiqishi kerak, foydalanuvchi Python/SQL worker'lariga esa tarmoq berilmaydi.

## Maxfiylik va lokal ishlash

- SQL faqat `SELECT` yoki `WITH ... SELECT`.
- Lokal Python notebook faqat localhost'da ishlaydi; internetga ochiq serverda `DATAFLOW_PYTHON_SANDBOX=docker` talab qilinadi. Docker deployment Python va SQL'ni alohida sandbox'da ishlatadi; sandbox sozlanmasa kod bajarish rad etiladi.
- AI kalitlarini `.env`da yoki local rejimda `backend\.env`da saqlang; `.env` fayllari zaxira/versiya nazoratiga kiritilmasin.
- `workspace` loyihalar va jadvallarni lokal diskda saqlaydi; undan zaxira nusxasi foydalanuvchi talabi bilan yaratiladi.
