(function () {
  "use strict";

  const translations = {
    "Ish maydoni": ["Рабочее пространство", "Workspace"],
    "Fayllar": ["Файлы", "Files"],
    "Tozalash": ["Очистка", "Cleaning"],
    "Grafiklar": ["Графики", "Charts"],
    "SQL muharriri": ["Редактор SQL", "SQL editor"],
    "Avto-statistika": ["Статистика", "Statistics"],
    "Notebook / Kod": ["Notebook / Код", "Notebook / Code"],
    "Dashboard": ["Панель", "Dashboard"],
    "Hisobot va import": ["Отчёты и импорт", "Reports and import"],
    "Yordam va FAQ": ["Помощь и FAQ", "Help and FAQ"],
    "Yordam": ["Помощь", "Help"],
    "Ma'lumotlar bilan ishlash": ["Работа с данными", "Data workspace"],
    "Maslahat": ["Совет", "Tip"],
    "Avval fayl yuklang, so'ng kerakli bo'limni tanlang.": [
      "Сначала загрузите файл, затем выберите нужный раздел.",
      "Upload a file first, then choose a section.",
    ],
    "Fayllar bazasi": ["Файлы", "Files"],
    "CSV yoki Excel faylini yuklang va tahlilni boshlang.": [
      "Загрузите CSV или Excel и начните анализ.",
      "Upload a CSV or Excel file to start analyzing.",
    ],
    "Loyiha": ["Проект", "Project"],
    "Yangi loyiha nomi": ["Название нового проекта", "New project name"],
    "Loyiha yaratish": ["Создать проект", "Create project"],
    "Fayllarni shu yerga tashlang": ["Перетащите файлы сюда", "Drop files here"],
    "yoki bosib tanlang (bir nechtasini birdan mumkin)": [
      "или нажмите, чтобы выбрать (можно несколько)",
      "or click to choose (multiple files allowed)",
    ],
    "Jadvallar (loyiha)": ["Таблицы (проект)", "Tables (project)"],
    "AI sozlamalari": ["Настройки ИИ", "AI settings"],
    "Namuna qatorlarni yuborish": ["Отправлять примеры строк", "Send sample rows"],
    "Esda saqlanadigan savollar soni": ["Число сохраняемых вопросов", "Questions to remember"],
    "AI so'rovlar limiti": ["Лимит запросов ИИ", "AI request limit"],
    "Saqlash": ["Сохранить", "Save"],
    "Bekor qilish": ["Отменить", "Undo"],
    "Tozalangan faylni yuklab olish": ["Скачать очищенный файл", "Download cleaned file"],
    "AI'dan so'rang": ["Спросить ИИ", "Ask AI"],
    "So'rash": ["Спросить", "Ask"],
    "Statistikani hisoblash": ["Рассчитать статистику", "Calculate statistics"],
    "Tozalash amali": ["Операция очистки", "Cleaning action"],
    "Oldin/keyin ko'rish": ["Предварительный просмотр", "Preview changes"],
    "Amalni qo'llash": ["Применить", "Apply"],
    "Pivot jadval": ["Сводная таблица", "Pivot table"],
    "Hisobot": ["Отчёт", "Report"],
    "Fayl tanlash": ["Выбрать файл", "Choose file"],
    "Import": ["Импорт", "Import"],
    "Eksport": ["Экспорт", "Export"],
    "Tez boshlash": ["Быстрый старт", "Quick start"],
    "Ko'p so'raladigan savollar": ["Часто задаваемые вопросы", "Frequently asked questions"],
    "Ma'lumotlar qayerda saqlanadi?": ["Где хранятся данные?", "Where is my data stored?"],
    "AI'ga namunaviy qatorlar yuboriladimi?": [
      "Отправляются ли ИИ примеры строк?",
      "Are sample rows sent to AI?",
    ],
    "Python xavfsizmi?": ["Безопасен ли Python?", "Is Python execution safe?"],
    "Parol yoki administratorni qanday tiklayman?": [
      "Как сбросить пароль или учётную запись администратора?",
      "How do I reset a password or administrator account?",
    ],
    "Excel varaqlarini tanlash mumkinmi?": [
      "Можно ли выбрать листы Excel?",
      "Can I choose Excel sheets?",
    ],
    "· ma'lumotni tozalash va tahlil qilish": ["· очистка и анализ данных", "· data cleaning and analysis"],
    "Foydalanuvchilar": ["Пользователи", "Users"],
    "Chiqish": ["Выйти", "Log out"],
    "Yordam va tez-tez so'raladigan savollar": ["Помощь и часто задаваемые вопросы", "Help and frequently asked questions"],
    "DataFlow AI'dan foydalanish va ma'lumotlaringizni himoyalash bo'yicha qisqa yo'riqnoma.": [
      "Краткое руководство по DataFlow AI и защите ваших данных.",
      "A quick guide to DataFlow AI and protecting your data.",
    ],
    "CSV yoki Excel faylini yuklang. Excel'da bitta yoki barcha varaqlarni yuklashingiz mumkin.": [
      "Загрузите CSV или Excel. В Excel можно выбрать один или все листы.",
      "Upload a CSV or Excel file. For Excel, choose one or all sheets.",
    ],
    "Jadvalni ko'ring, sahifalang va ustun sarlavhasini bosib saralang.": [
      "Просматривайте и сортируйте таблицу по страницам и заголовкам столбцов.",
      "Browse pages and sort the table by clicking a column heading.",
    ],
    "Tozalash amallarini avval ko'rib chiqing, so'ng tasdiqlab qo'llang.": [
      "Сначала просмотрите изменения очистки, затем подтвердите их.",
      "Preview cleaning changes first, then confirm to apply them.",
    ],
    "SQL, grafik, pivot va dashboard orqali tahlil qiling; natijalarni hisobotga chiqaring.": [
      "Анализируйте с помощью SQL, графиков, сводных таблиц и панели; экспортируйте отчёты.",
      "Analyze with SQL, charts, pivots, and dashboards; export the results as reports.",
    ],
    "Mahalliy ishga tushirishda ma'lumotlar ilovaning workspace papkasida saqlanadi. Serverda har bir foydalanuvchining alohida workspace'i bor.": [
      "Локально данные хранятся в папке приложения. На сервере у каждого пользователя отдельное рабочее пространство.",
      "Locally, data is stored in the app workspace. On a server, each user has a separate workspace.",
    ],
    "AI sozlamalaridagi maxfiylik tugmasi orqali namunalarni yuborishni o'chiring. O'chirilganda modelga sxema va savol yuboriladi, qatorlar emas.": [
      "Отключите отправку примеров в настройках конфиденциальности ИИ. Тогда модели передаются схема и вопрос, но не строки.",
      "Disable sample sharing in AI privacy settings. The model then receives the schema and question, not data rows.",
    ],
    "Server rejimida kod alohida, tarmoqsiz Docker konteynerida cheklangan xotira, protsessor, jarayon va vaqt bilan bajariladi. Mahalliy rejim faqat localhost'da ishlashi kerak.": [
      "На сервере код выполняется в отдельном Docker-контейнере без сети и с лимитами ресурсов. Локальный режим должен быть доступен только через localhost.",
      "On a server, code runs in a separate network-isolated Docker container with resource limits. Local mode must stay on localhost.",
    ],
    "Administrator boshqa foydalanuvchining parolini qayta o'rnatishi mumkin. Hech bo'lmaganda bitta faol administratorni o'chirib bo'lmaydi.": [
      "Администратор может сбросить пароль другого пользователя. Нельзя отключить последнего активного администратора.",
      "An administrator can reset another user's password. The last active administrator cannot be disabled.",
    ],
    "Ha. Yuklashdan oldin varaqlar ro'yxatidan bittasini yoki barchasini tanlang.": [
      "Да. Перед загрузкой выберите один или все листы.",
      "Yes. Choose one or all sheets before importing.",
    ],
    "Provider": ["Провайдер", "Provider"],
    "Avtomatik": ["Автоматически", "Automatic"],
    "Yangi loyihani yaratish": ["Создать новый проект", "Create a new project"],
    "Fayllarni shu yerga tashlang": ["Перетащите файлы сюда", "Drop files here"],
    "yoki bosib tanlang (bir nechtasini birdan mumkin)": [
      "или нажмите, чтобы выбрать (можно несколько)",
      "or click to choose (multiple files allowed)",
    ],
    ".csv yoki .xlsx, har biri 1 GB gacha · Excel'dan bir yoki barcha varaqlarni tanlang": [
      ".csv или .xlsx, до 1 ГБ каждый · выберите один или все листы Excel",
      ".csv or .xlsx, up to 1 GB each · choose one or all Excel sheets",
    ],
    "SQL muharriri": ["Редактор SQL", "SQL editor"],
    "So'rov yozing yoki AI'dan jadvalingiz haqida so'rang.": [
      "Напишите запрос или задайте ИИ вопрос о таблице.",
      "Write a query or ask AI about your table.",
    ],
    "(faol jadval bo'yicha)": ["(текущая таблица)", "(active table)"],
    "Masalan: qaysi hududda o'rtacha narx eng baland?": [
      "Например: в каком регионе самая высокая средняя цена?",
      "For example: which region has the highest average price?",
    ],
    "Bajarish (Ctrl+Enter)": ["Выполнить (Ctrl+Enter)", "Run (Ctrl+Enter)"],
    "Ustunlar, taqsimotlar va ma'lumotlar orasidagi bog'liqlik.": [
      "Столбцы, распределения и связи между данными.",
      "Columns, distributions, and relationships in the data.",
    ],
    "Topilgan muammolarni ko'rib, tavsiya etilgan amallar bilan bir tugmada tuzating.": [
      "Просмотрите найденные проблемы и исправьте их рекомендованными действиями.",
      "Review detected issues and fix them with recommended actions.",
    ],
    "Barcha matnlardan chetki bo'shliqni olish": ["Удалить пробелы по краям текста", "Trim surrounding whitespace"],
    "Ustundagi matnni normallashtirish": ["Нормализовать текст в столбце", "Normalize text in a column"],
    "Aniq takror qatorlarni olib tashlash": ["Удалить точные дубликаты строк", "Remove exact duplicate rows"],
    "Tanlangan ustunlar bo'yicha takrorlarni olib tashlash": ["Удалить дубликаты по выбранным столбцам", "Remove duplicates by selected columns"],
    "Bo'sh qiymatli qatorni olib tashlash": ["Удалить строки с пропусками", "Remove rows with missing values"],
    "Bo'sh qiymatni to'ldirish": ["Заполнить пропуски", "Fill missing values"],
    "Bo'shni “noma'lum” bilan to'ldirish": ["Заполнить пропуски значением «неизвестно»", "Fill missing values with “unknown”"],
    "Noto'g'ri raqam/sanani bo'shatish": ["Заменить неверные числа/даты на пустые", "Replace invalid numbers/dates with empty values"],
    "Raqam turiga o'tkazish": ["Преобразовать в число", "Convert to number"],
    "Sanani format bilan o'tkazish": ["Преобразовать дату по формату", "Convert date using a format"],
    "Sanani ISO (YYYY-MM-DD) qilish": ["Преобразовать дату в ISO (YYYY-MM-DD)", "Convert date to ISO (YYYY-MM-DD)"],
    "Ustunni qayta nomlash": ["Переименовать столбец", "Rename column"],
    "Ustunni olib tashlash": ["Удалить столбец", "Drop column"],
    "Ustunni ikkiga bo'lish": ["Разделить столбец на два", "Split a column in two"],
    "Bir nechta ustunni birlashtirish": ["Объединить несколько столбцов", "Merge multiple columns"],
    "Qiymatlarni ro'yxat bo'yicha almashtirish": ["Заменить значения по списку", "Replace values using a mapping"],
    "Ustunlar (bir nechta tanlash mumkin)": ["Столбцы (можно выбрать несколько)", "Columns (select multiple)"],
    "Matnni o'zgartirish": ["Изменение текста", "Text transformation"],
    "Chetki bo'shliqni olish": ["Удалить пробелы по краям", "Trim whitespace"],
    "Kichik harf": ["Строчные", "Lowercase"],
    "Katta harf": ["Заглавные", "Uppercase"],
    "Ketma-ket bo'shliqni qisqartirish": ["Сократить повторяющиеся пробелы", "Collapse repeated spaces"],
    "To'ldirish usuli": ["Способ заполнения", "Fill method"],
    "Eng ko'p uchraydigan": ["Наиболее частое", "Most frequent"],
    "Berilgan qiymat": ["Заданное значение", "Custom value"],
    "Yangi ustun nomi": ["Новое имя столбца", "New column name"],
    "Ikkinchi ustun nomi": ["Имя второго столбца", "Second column name"],
    "Ajratgich belgisi": ["Разделитель", "Separator"],
    "O'nlik ajratgichi": ["Десятичный разделитель", "Decimal separator"],
    "Minglik ajratgichi (ixtiyoriy)": ["Разделитель тысяч (необязательно)", "Thousands separator (optional)"],
    "Sana formati (ixtiyoriy)": ["Формат даты (необязательно)", "Date format (optional)"],
    "Almashtirish ro'yxati (JSON)": ["Список замен (JSON)", "Replacement map (JSON)"],
    "Manba ustunlarini o'chirish": ["Удалить исходные столбцы", "Remove source columns"],
    "Retseptga qadam qo'shish": ["Добавить шаг в рецепт", "Add recipe step"],
    "Tozalash retseptlari": ["Рецепты очистки", "Cleaning recipes"],
    "Retsept nomi": ["Название рецепта", "Recipe name"],
    "Retseptni saqlash": ["Сохранить рецепт", "Save recipe"],
    "Saqlangan retsept yo'q": ["Нет сохранённых рецептов", "No saved recipes"],
    "Retseptni ko'rish": ["Предпросмотр рецепта", "Preview recipe"],
    "Retseptni qo'llash": ["Применить рецепт", "Apply recipe"],
    "Deyarli takror qatorlarni topish": ["Найти почти дублирующиеся строки", "Find near-duplicate rows"],
    "Takrorlarni topish": ["Найти дубликаты", "Find duplicates"],
    "Topilgan muammolar": ["Найденные проблемы", "Detected issues"],
    "Ma'lumot ko'rinishi": ["Предпросмотр данных", "Data preview"],
    "Jadval sahifalari": ["Страницы таблицы", "Table pages"],
    "Qator/sahifa": ["Строк на странице", "Rows per page"],
    "Ustun sarlavhasini bosib saralang.": ["Нажмите на заголовок столбца для сортировки.", "Click a column heading to sort."],
    "Oldingi": ["Назад", "Previous"],
    "Keyingi": ["Далее", "Next"],
    "Ustunlar": ["Столбцы", "Columns"],
    "O'zgarishlar tarixi": ["История изменений", "Change history"],
    "SQL natijasi yoki AI javobidan ustunlarni tanlab grafik chizing.": [
      "Выберите столбцы из результата SQL или ответа ИИ, чтобы построить график.",
      "Choose columns from SQL results or an AI answer to chart.",
    ],
    "Interaktiv vizualizatsiya": ["Интерактивная визуализация", "Interactive visualization"],
    "Grafik yaratish uchun SQL bo'limida so'rovni bajaring, so'ng natija jadvalidagi": [
      "Чтобы построить график, выполните SQL-запрос и используйте кнопку в таблице результата.",
      "Run a query in SQL, then use the chart button in its results table.",
    ],
    "Grafik chizish": ["Построить график", "Create chart"],
    "Qator bo'yicha": ["Строки", "Rows"],
    "Ustun bo'yicha (ixtiyoriy)": ["Столбцы (необязательно)", "Columns (optional)"],
    "Qiymat": ["Значение", "Value"],
    "Hisoblash": ["Агрегация", "Aggregation"],
    "Yig'indi": ["Сумма", "Sum"],
    "Soni": ["Количество", "Count"],
    "O'rtacha": ["Среднее", "Mean"],
    "Minimum": ["Минимум", "Minimum"],
    "Maksimum": ["Максимум", "Maximum"],
    "Pivot hisoblash": ["Рассчитать сводную таблицу", "Calculate pivot"],
    "Hisobot va qo'shimcha vositalar": ["Отчёты и инструменты", "Reports and tools"],
    "Hisobot, Excel, import va zaxira nusxasi.": ["Отчёты, Excel, импорт и резервное копирование.", "Reports, Excel, imports, and backups."],
    "Eksport va g'ayritabiiy qiymatlar": ["Экспорт и выбросы", "Export and outliers"],
    "HTML hisobotini yuklab olish": ["Скачать HTML-отчёт", "Download HTML report"],
    "PDF uchun chop etish": ["Печать в PDF", "Print to PDF"],
    "Ko'p varaqli Excel hisobot": ["Многостраничный отчёт Excel", "Multi-sheet Excel report"],
    "Raqamli ustun": ["Числовой столбец", "Numeric column"],
    "IQR koeffitsiyenti": ["Коэффициент IQR", "IQR multiplier"],
    "Tekshirish": ["Проверить", "Check"],
    "Chegaraga keltirish": ["Ограничить значения", "Clip to bounds"],
    "Qatorlarni olib tashlash": ["Удалить строки", "Remove rows"],
    "Hisobot ko'rinishi va kunlik yangilash": ["Отчёт и ежедневное обновление", "Report and daily refresh"],
    "Hisobot sarlavhasi": ["Заголовок отчёта", "Report title"],
    "Kunlik ish vaqti": ["Время ежедневного запуска", "Daily run time"],
    "Kunlik hisobotni yangilash": ["Обновлять отчёт ежедневно", "Refresh reports daily"],
    "HTML va Excel nusxalarini saqlash": ["Сохранять копии HTML и Excel", "Save HTML and Excel copies"],
    "Sozlamalarni saqlash": ["Сохранить настройки", "Save settings"],
    "Hisobotlarni hozir yangilash": ["Обновить отчёты сейчас", "Refresh reports now"],
    "Shablonlar galereyasi": ["Галерея шаблонов", "Template gallery"],
    "Faol jadval ustunlarini tanlang. Natijalar tekshirish uchun ko'rsatkich bo'lib, hukm emas va audit o'rnini bosmaydi.": [
      "Выберите столбцы активной таблицы. Результаты — только индикаторы для проверки, не вывод и не замена аудита.",
      "Choose columns from the active table. Results are indicators to verify, not conclusions or a substitute for an audit.",
    ],
    "Havola orqali yuklash": ["Загрузить по ссылке", "Import from URL"],
    "Ochiq CSV yoki XLSX havolasi": ["Публичная ссылка на CSV или XLSX", "Public CSV or XLSX URL"],
    "Yuklash": ["Загрузить", "Upload"],
    "PostgreSQL yoki MySQL'dan import": ["Импорт из PostgreSQL или MySQL", "Import from PostgreSQL or MySQL"],
    "Server manzili": ["Адрес сервера", "Server address"],
    "Port (ixtiyoriy)": ["Порт (необязательно)", "Port (optional)"],
    "Baza nomi": ["Имя базы данных", "Database name"],
    "Foydalanuvchi": ["Пользователь", "Username"],
    "Parol (saqlanmaydi)": ["Пароль (не сохраняется)", "Password (not saved)"],
    "Faqat SELECT so'rovi": ["Только запрос SELECT", "SELECT query only"],
    "Import qilish": ["Импортировать", "Import"],
    "Zaxira nusxasi": ["Резервная копия", "Backup"],
    "Zaxira yaratish": ["Создать резервную копию", "Create backup"],
    "Ro'yxatni yangilash": ["Обновить список", "Refresh list"],
    "Excel varaqlarini tanlang": ["Выберите листы Excel", "Choose Excel sheets"],
    "Bir yoki bir nechta varaq tanlang. “Barcha varaqlar”ni tanlasangiz, har biri alohida jadval bo'ladi.": [
      "Выберите один или несколько листов. При выборе «Все листы» каждый станет отдельной таблицей.",
      "Select one or more sheets. Choosing “All sheets” imports each as a separate table.",
    ],
    "Barcha varaqlar": ["Все листы", "All sheets"],
    "Tanlanmagan": ["Не выбрано", "Not selected"],
    "Kirish": ["Войти", "Sign in"],
    "Administrator yaratish": ["Создать администратора", "Create administrator"],
    "birinchi administrator": ["первый администратор", "first administrator"],
    "Login": ["Логин", "Username"],
    "Parol": ["Пароль", "Password"],
    "Administrator yaratish kodi (server talab qilsa)": ["Код создания администратора (если требуется сервером)", "Admin setup token (if required by server)"],
    "Foydalanuvchilar va audit": ["Пользователи и аудит", "Users and audit"],
    "Yopish": ["Закрыть", "Close"],
    "Rol": ["Роль", "Role"],
    "Analitik": ["Аналитик", "Analyst"],
    "Ko'ruvchi": ["Наблюдатель", "Viewer"],
    "Foydalanuvchi qo'shish": ["Добавить пользователя", "Add user"],
    "Holat": ["Статус", "Status"],
    "Oxirgi audit hodisalari": ["Последние события аудита", "Recent audit events"],
    "DataFlow AI bilan tanishing": ["Знакомство с DataFlow AI", "Get started with DataFlow AI"],
    "Keyingi": ["Далее", "Next"],
    "Orqaga": ["Назад", "Back"],
    "Boshlash": ["Начать", "Get started"],
    "DataFlow AI — tizimga kirish": ["DataFlow AI — вход", "DataFlow AI — sign in"],
    "DataFlow AI — birinchi administrator": ["DataFlow AI — первый администратор", "DataFlow AI — first administrator"],
    "Davom etish uchun hisobingiz bilan kiring.": ["Войдите в свою учётную запись, чтобы продолжить.", "Sign in to your account to continue."],
    "Xavfsiz parol bilan birinchi administratorni yarating. Parol xeshlangan holda saqlanadi.": [
      "Создайте первого администратора с надёжным паролем. Пароль хранится в виде хеша.",
      "Create the first administrator with a strong password. Passwords are stored as hashes.",
    ],
    "Administrator yaratildi. Endi tizimga kiring.": ["Администратор создан. Теперь войдите.", "Administrator created. You can now sign in."],
    "1 / 4 · Til va loyiha": ["1 / 4 · Язык и проект", "1 / 4 · Language and project"],
    "Tilni yuqoridagi tanlagichdan belgilang, faol loyiha esa jadvallar va panellarni ajratib saqlaydi.": [
      "Выберите язык выше; активный проект хранит свои таблицы и панели отдельно.",
      "Choose a language above; the active project keeps its tables and dashboards separate.",
    ],
    "2 / 4 · Ma'lumot yuklash": ["2 / 4 · Загрузка данных", "2 / 4 · Import data"],
    "3 / 4 · Tekshirish va tozalash": ["3 / 4 · Проверка и очистка", "3 / 4 · Review and clean"],
    "Jadvalni ko'ring, sahifalang va amallarni qo'llashdan oldin natijani oldindan ko'ring.": [
      "Просматривайте таблицу по страницам и проверяйте изменения перед применением.",
      "Browse the table and preview changes before applying them.",
    ],
    "4 / 4 · Tahlil va xavfsizlik": ["4 / 4 · Анализ и безопасность", "4 / 4 · Analysis and security"],
    "SQL, AI, grafik va hisobotlardan foydalaning. AI maxfiylik sozlamalarini tekshiring; administratorlar foydalanuvchi va audit jurnalini boshqaradi.": [
      "Используйте SQL, ИИ, графики и отчёты. Проверьте настройки конфиденциальности ИИ; администраторы управляют пользователями и аудитом.",
      "Use SQL, AI, charts, and reports. Review AI privacy settings; administrators manage users and the audit log.",
    ],
    "CSV yoki Excel faylini yuklang; katta Excel fayllari uchun kerakli varaqlarni tanlang.": [
      "Загрузите CSV или Excel; для больших файлов Excel выберите нужные листы.",
      "Upload a CSV or Excel file; choose the required sheets for large Excel files.",
    ],
    "Jadvalni ko'ring, sahifalang, ustun sarlavhasini bosib saralang.": [
      "Просматривайте таблицу по страницам и сортируйте по заголовкам столбцов.",
      "Browse table pages and sort by clicking column headings.",
    ],
    "Ha. Yuklashdan oldin varaqlar ro'yxatidan bittasini yoki barchasini tanlang.": [
      "Да. Перед загрузкой выберите один или все листы.",
      "Yes. Choose one or all sheets before importing.",
    ],
    "Python kataklari": ["Ячейки Python", "Python cells"],
    "Mahalliy rejimda kod localhost'dagi doimiy kerneldan foydalanadi. Server rejimida har bir bajarish alohida, tarmoqsiz Docker konteynerida (30 soniya, 1 GiB xotira, 1 CPU) bajariladi. O'zgaruvchilar: df (faol jadval), tables (hamma jadvallar), pd, np. Faqat o'zingiz tushungan yoki o'qib chiqqan kodni bajaring. Xavfsizlik siyosati fayl, tarmoq va boshqa jarayon amallarini cheklaydi.": [
      "В локальном режиме используется постоянное ядро localhost. На сервере каждый запуск выполняется в отдельном Docker-контейнере без сети (30 секунд, 1 ГиБ памяти, 1 CPU). Переменные: df (активная таблица), tables (все таблицы), pd, np. Запускайте только понятный вам код. Политика безопасности ограничивает доступ к файлам, сети и другим процессам.",
      "Local mode uses a persistent localhost kernel. On a server, each run uses a separate network-isolated Docker container (30 seconds, 1 GiB memory, 1 CPU). Variables: df (active table), tables (all tables), pd, np. Run only code you understand. Security policy restricts file, network, and other-process access.",
    ],
    "AI kod yozsin: masalan, hududlar bo'yicha o'rtacha narxni hisoblab, eng qimmat 5 tasini ko'rsat": [
      "ИИ, напиши код: например, рассчитай среднюю цену по регионам и покажи 5 самых дорогих",
      "Ask AI to write code, e.g. calculate average price by region and show the top 5",
    ],
    "AI kod yozsin": ["Пусть ИИ напишет код", "Ask AI to write code"],
    "+ Kod katagi": ["+ Ячейка кода", "+ Code cell"],
    "+ Markdown": ["+ Markdown", "+ Markdown"],
    "Hammasini bajarish": ["Выполнить всё", "Run all"],
    "Qayta boshlash": ["Перезапустить", "Restart"],
    "To'xtatish": ["Остановить", "Stop"],
    "Import (.py/.ipynb)": ["Импорт (.py/.ipynb)", "Import (.py/.ipynb)"],
    ".py eksport": ["Экспорт .py", "Export .py"],
    ".ipynb eksport": ["Экспорт .ipynb", "Export .ipynb"],
    "Tanlangan katakdan oldingilarini bajarish": [
      "Выполнять ячейки до выбранной включительно",
      "Run cells up to and including the selected cell",
    ],
    "Bajarilmoqda...": ["Выполняется...", "Running..."],
    "AI tahlil qilyapti...": ["ИИ анализирует...", "AI is analyzing..."],
    "AI kod yozyapti...": ["ИИ пишет код...", "AI is writing code..."],
    "Ko'rish": ["Просмотр", "View"],
    "Tahrirlash": ["Редактировать", "Edit"],
    "Kernel qayta ishga tushirildi; o'zgaruvchilar tozalandi.": [
      "Ядро перезапущено; переменные очищены.",
      "Kernel restarted; variables cleared.",
    ],
    "Faol bajarish yo'q.": ["Нет активного выполнения.", "No active execution."],
    "Bajarish to'xtatildi.": ["Выполнение остановлено.", "Execution stopped."],
    "Dashboardga qo'shish": ["Добавить на панель", "Add to dashboard"],
    "HTML eksport": ["Экспорт HTML", "Export HTML"],
    "Hammasini yangilash": ["Обновить всё", "Refresh all"],
    "Global filtrlar": ["Глобальные фильтры", "Global filters"],
    "Filtrlarni qo'llash va saqlash": ["Применить и сохранить фильтры", "Apply and save filters"],
    "Hali panel yo'q. SQL natijasi tagidagi \"Dashboardga qo'shish\" tugmasini bosing.": [
      "Панелей пока нет. Нажмите «Добавить на панель» под результатом SQL.",
      "No panels yet. Click “Add to dashboard” below an SQL result.",
    ],
    "Hisoblanmoqda...": ["Вычисление...", "Calculating..."],
    "Panel nomi:": ["Название панели:", "Panel title:"],
    "Panel SQL:": ["SQL панели:", "Panel SQL:"],
    "panelini o'chirasizmi?": ["удалить панель?", "delete this panel?"],
    "KPI kartochkasi sifatida qo'shilsinmi? (Bekor qilish = grafik/jadval)": [
      "Добавить как KPI-карточку? (Отмена = график/таблица)",
      "Add as a KPI card? (Cancel = chart/table)",
    ],
    "Yuqoriga": ["Вверх", "Move up"],
    "Pastga": ["Вниз", "Move down"],
    "Kengligi": ["Ширина", "Width"],
    "Yangilash": ["Обновить", "Refresh"],
    "O'chirish": ["Удалить", "Delete"],
    "Nusxalash": ["Копировать", "Duplicate"],
    "Bajarish (Shift+Enter)": ["Выполнить (Shift+Enter)", "Run (Shift+Enter)"],
    "HTML hisobotini yuklab olish": ["Скачать HTML-отчёт", "Download HTML report"],
    "Shablon hisoblanmoqda...": ["Вычисление шаблона...", "Calculating template..."],
    "Bu amal yangi tozalash versiyasini saqlaydi. Davom etasizmi?": [
      "Это действие сохранит новую версию очищенных данных. Продолжить?",
      "This action saves a new cleaned-data version. Continue?",
    ],
    "Tekshirilmoqda...": ["Проверка...", "Checking..."],
    "Zaxira yaratilmoqda...": ["Создание резервной копии...", "Creating backup..."],
    "Chizish uchun qiymat yo'q": ["Нет значений для построения графика", "No values to chart"],
    "Til": ["Язык", "Language"],
  };

  const sourceText = new WeakMap();
  const translatedText = new WeakMap();
  const translatedLocale = new WeakMap();
  const attributeKeys = ["placeholder", "title", "aria-label"];
  let currentLocale = -1;

  window.DFTranslate = (text) => {
    const entry = translations[String(text).trim()];
    return currentLocale < 0 || !entry ? text : entry[currentLocale];
  };

  function applyLanguage(language) {
    const locale = language === "ru" ? 0 : language === "en" ? 1 : -1;
    currentLocale = locale;
    document.documentElement.lang = language;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || parent.closest("script,style,textarea,pre,code")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let node;
    while ((node = walker.nextNode())) {
      const current = node.nodeValue;
      const lastTranslation = translatedText.get(node);
      if (lastTranslation === current && translatedLocale.get(node) === language) continue;
      const original = lastTranslation === current && sourceText.has(node)
        ? sourceText.get(node)
        : current;
      sourceText.set(node, original);
      const trimmed = original.trim();
      const entry = translations[trimmed];
      const value = locale < 0 || !entry ? trimmed : entry[locale];
      const left = original.match(/^\s*/)[0];
      const right = original.match(/\s*$/)[0];
      node.nodeValue = `${left}${value}${right}`;
      translatedText.set(node, node.nodeValue);
      translatedLocale.set(node, language);
    }
    document.querySelectorAll("input,button,select,textarea").forEach((element) => {
      for (const attribute of attributeKeys) {
        const value = element.getAttribute(attribute);
        if (!value) continue;
        const key = `data-i18n-original-${attribute}`;
        if (!element.hasAttribute(key)) element.setAttribute(key, value);
        const original = element.getAttribute(key);
        const entry = translations[original.trim()];
        element.setAttribute(attribute, locale < 0 || !entry ? original : entry[locale]);
      }
    });
  }

  const selector = document.getElementById("languageSwitcher");
  if (!selector) return;
  let saved = "uz";
  try {
    saved = localStorage.getItem("dataflow-language") || "uz";
  } catch {}
  selector.value = ["uz", "ru", "en"].includes(saved) ? saved : "uz";
  selector.addEventListener("change", () => {
    try {
      localStorage.setItem("dataflow-language", selector.value);
    } catch {}
    applyLanguage(selector.value);
  });
  applyLanguage(selector.value);
  const observer = new MutationObserver(() => applyLanguage(selector.value));
  observer.observe(document.body, { childList: true, characterData: true, subtree: true });
})();
