from __future__ import annotations

from typing import Any


TEMPLATES = [
    {
        "id": "marketing-rfm",
        "category": "Marketing",
        "title": "RFM segmentatsiya",
        "description": "Mijozlarning oxirgi xaridi, xaridlar soni va sarfini jamlaydi.",
        "fields": [
            {"id": "customer", "label": "Mijoz", "kind": "text"},
            {"id": "date", "label": "Xarid sanasi", "kind": "date"},
            {"id": "amount", "label": "Xarid summasi", "kind": "number"},
        ],
    },
    {
        "id": "marketing-cohort",
        "category": "Marketing",
        "title": "Kohorta tahlili",
        "description": "Mijozning ilk faollik oyi va keyingi oylar bo'yicha faolligini hisoblaydi.",
        "fields": [
            {"id": "customer", "label": "Mijoz", "kind": "text"},
            {"id": "date", "label": "Faollik sanasi", "kind": "date"},
        ],
    },
    {
        "id": "marketing-funnel",
        "category": "Marketing",
        "title": "Voronka",
        "description": "Har bir bosqichdagi noyob foydalanuvchilarni sanaydi.",
        "fields": [
            {"id": "user", "label": "Foydalanuvchi", "kind": "text"},
            {"id": "stage", "label": "Voronka bosqichi", "kind": "text"},
        ],
    },
    {
        "id": "marketing-campaign",
        "category": "Marketing",
        "title": "Kampaniya samaradorligi",
        "description": "Kampaniya bo'yicha sarf, konversiya va birlik sarfini jamlaydi.",
        "fields": [
            {"id": "campaign", "label": "Kampaniya", "kind": "text"},
            {"id": "spend", "label": "Sarf", "kind": "number"},
            {"id": "conversions", "label": "Konversiyalar", "kind": "number"},
        ],
    },
    {
        "id": "finance-balance",
        "category": "Moliya",
        "title": "Balans / yig'indi mosligi",
        "description": "Debet va kredit yig'indilarining farqini ko'rsatadi.",
        "fields": [
            {"id": "debit", "label": "Debet", "kind": "number"},
            {"id": "credit", "label": "Kredit", "kind": "number"},
        ],
    },
    {
        "id": "finance-duplicates",
        "category": "Moliya",
        "title": "Takroriy tranzaksiyalar",
        "description": "Tanlangan maydonlar bo'yicha takroriy yozuvlarni topishga yordam beradi.",
        "fields": [
            {"id": "date", "label": "Tranzaksiya sanasi", "kind": "date"},
            {"id": "amount", "label": "Summa", "kind": "number"},
            {"id": "reference", "label": "Hisob / tavsif (ixtiyoriy)", "kind": "text", "optional": True},
        ],
    },
    {
        "id": "finance-unusual",
        "category": "Moliya",
        "title": "G'alati summalar",
        "description": "O'rtachadan uch standart og'ishdan uzoq qiymatlarni ajratadi.",
        "fields": [{"id": "amount", "label": "Tranzaksiya summasi", "kind": "number"}],
    },
]


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _column(mapping: dict[str, str], key: str) -> str:
    return quote_identifier(mapping[key])


def build_template_query(template_id: str, mapping: dict[str, str]) -> tuple[str, str]:
    c = lambda key: _column(mapping, key)
    if template_id == "marketing-rfm":
        sql = (
            "WITH metrics AS ("
            f"SELECT {c('customer')} AS customer, "
            f"date_diff('day', CAST(MAX({c('date')}) AS DATE), CURRENT_DATE) AS recency_days, "
            f"COUNT(*) AS frequency, SUM(TRY_CAST({c('amount')} AS DOUBLE)) AS monetary "
            f"FROM data GROUP BY {c('customer')}), scored AS (SELECT *, "
            "5 - NTILE(4) OVER (ORDER BY recency_days ASC) AS r_score, "
            "5 - NTILE(4) OVER (ORDER BY frequency DESC) AS f_score, "
            "5 - NTILE(4) OVER (ORDER BY monetary DESC) AS m_score FROM metrics) "
            "SELECT *, CONCAT(r_score, f_score, m_score) AS rfm_segment "
            "FROM scored ORDER BY monetary DESC LIMIT 1000"
        )
        py = (
            f"rfm = df.groupby({mapping['customer']!r}).agg("
            f"recency=({mapping['date']!r}, 'max'), "
            f"frequency=({mapping['date']!r}, 'count'), "
            f"monetary=({mapping['amount']!r}, 'sum'))\n"
            "rfm['recency_days'] = (pd.Timestamp.today().normalize() - rfm['recency']).dt.days\n"
            "for metric in ['recency_days', 'frequency', 'monetary']:\n"
            "    rfm[metric + '_score'] = pd.qcut(rfm[metric].rank(method='first'), "
            "4, labels=False, duplicates='drop') + 1\n"
            "rfm['recency_days_score'] = 5 - rfm['recency_days_score']\n"
            "rfm['rfm_segment'] = rfm[['recency_days_score', 'frequency_score', "
            "'monetary_score']].astype(str).agg(''.join, axis=1)\n"
            "rfm.sort_values('monetary', ascending=False)"
        )
    elif template_id == "marketing-cohort":
        sql = (
            f"WITH activity AS (SELECT {c('customer')} AS customer, "
            f"date_trunc('month', CAST({c('date')} AS DATE)) AS active_month FROM data), "
            f"cohorts AS (SELECT customer, MIN(active_month) AS cohort_month FROM activity GROUP BY customer) "
            f"SELECT cohorts.cohort_month, activity.active_month, "
            f"date_diff('month', cohorts.cohort_month, activity.active_month) AS month_number, "
            f"COUNT(DISTINCT activity.customer) AS active_customers "
            f"FROM activity JOIN cohorts USING (customer) "
            f"GROUP BY 1, 2, 3 ORDER BY 1, 3 LIMIT 1000"
        )
        py = (
            f"cohort = df.assign(activity_month=df[{mapping['date']!r}].dt.to_period('M'))\n"
            f"cohort['cohort_month'] = cohort.groupby({mapping['customer']!r})"
            f"['activity_month'].transform('min')\n"
            "cohort['month_number'] = ((cohort['activity_month'].dt.year - "
            "cohort['cohort_month'].dt.year) * 12 + cohort['activity_month'].dt.month - "
            "cohort['cohort_month'].dt.month)\n"
            f"cohort.groupby(['cohort_month', 'month_number'])[{mapping['customer']!r}]"
            ".nunique().unstack(fill_value=0)"
        )
    elif template_id == "marketing-funnel":
        sql = (
            f"SELECT {c('stage')} AS stage, COUNT(DISTINCT {c('user')}) AS users "
            f"FROM data GROUP BY {c('stage')} ORDER BY users DESC LIMIT 1000"
        )
        py = f"df.groupby({mapping['stage']!r})[{mapping['user']!r}].nunique().sort_values(ascending=False)"
    elif template_id == "marketing-campaign":
        sql = (
            f"SELECT {c('campaign')} AS campaign, "
            f"SUM(TRY_CAST({c('spend')} AS DOUBLE)) AS total_spend, "
            f"SUM(TRY_CAST({c('conversions')} AS DOUBLE)) AS conversions, "
            f"SUM(TRY_CAST({c('spend')} AS DOUBLE)) / "
            f"NULLIF(SUM(TRY_CAST({c('conversions')} AS DOUBLE)), 0) AS cost_per_conversion "
            f"FROM data GROUP BY {c('campaign')} ORDER BY conversions DESC LIMIT 1000"
        )
        py = (
            f"campaign = df.groupby({mapping['campaign']!r}).agg("
            f"spend=({mapping['spend']!r}, 'sum'), "
            f"conversions=({mapping['conversions']!r}, 'sum'))\n"
            "campaign['cost_per_conversion'] = campaign['spend'] / "
            "campaign['conversions'].replace(0, pd.NA)\ncampaign"
        )
    elif template_id == "finance-balance":
        sql = (
            f"SELECT SUM(TRY_CAST({c('debit')} AS DOUBLE)) AS debit_total, "
            f"SUM(TRY_CAST({c('credit')} AS DOUBLE)) AS credit_total, "
            f"SUM(TRY_CAST({c('debit')} AS DOUBLE)) - "
            f"SUM(TRY_CAST({c('credit')} AS DOUBLE)) AS difference FROM data"
        )
        py = (
            f"debit_total = pd.to_numeric(df[{mapping['debit']!r}], errors='coerce').sum()\n"
            f"credit_total = pd.to_numeric(df[{mapping['credit']!r}], errors='coerce').sum()\n"
            "difference = debit_total - credit_total\n"
            "{'debit_total': debit_total, 'credit_total': credit_total, 'difference': difference}"
        )
    elif template_id == "finance-duplicates":
        fields = ["date", "amount"] + (["reference"] if mapping.get("reference") else [])
        group = ", ".join(c(field) for field in fields)
        select = ", ".join(f"{c(field)} AS {field}" for field in fields)
        sql = (
            f"SELECT {select}, COUNT(*) AS occurrences FROM data "
            f"GROUP BY {group} HAVING COUNT(*) > 1 ORDER BY occurrences DESC LIMIT 1000"
        )
        py_columns = ", ".join(repr(mapping[field]) for field in fields)
        py = f"df.groupby([{py_columns}]).size().loc[lambda counts: counts > 1].sort_values(ascending=False)"
    elif template_id == "finance-unusual":
        sql = (
            f"WITH sample_values AS (SELECT *, TRY_CAST({c('amount')} AS DOUBLE) AS _amount FROM data), "
            "bounds AS (SELECT AVG(_amount) AS mean, STDDEV_POP(_amount) AS deviation FROM sample_values) "
            "SELECT sample_values.* FROM sample_values CROSS JOIN bounds "
            "WHERE ABS(sample_values._amount - bounds.mean) > 3 * bounds.deviation "
            "ORDER BY ABS(sample_values._amount - bounds.mean) DESC LIMIT 1000"
        )
        py = (
            f"amount = pd.to_numeric(df[{mapping['amount']!r}], errors='coerce')\n"
            "amount[(amount - amount.mean()).abs() > 3 * amount.std(ddof=0)]"
        )
    else:
        raise KeyError(template_id)
    return sql, py


def template_result(template_id: str, mapping: dict[str, str], columns: list[dict[str, Any]]) -> dict[str, Any]:
    template = next((item for item in TEMPLATES if item["id"] == template_id), None)
    if template is None:
        raise KeyError(template_id)
    available = {column["name"]: column["type"] for column in columns}
    expected = {field["id"]: field for field in template["fields"]}
    unknown_keys = set(mapping) - set(expected)
    if unknown_keys:
        raise ValueError(f"Noma'lum maydon: {', '.join(sorted(unknown_keys))}")
    cleaned = {}
    for field in template["fields"]:
        value = mapping.get(field["id"])
        if not value and field.get("optional"):
            continue
        if not isinstance(value, str) or value not in available:
            raise ValueError(f"'{field['label']}' uchun ustun tanlang")
        kind = available[value]
        if kind != field["kind"] and not (field["kind"] == "text" and kind in ("text", "empty")):
            raise ValueError(f"'{field['label']}' maydoni uchun {field['kind']} turidagi ustun kerak")
        cleaned[field["id"]] = value
    sql, python = build_template_query(template_id, cleaned)
    return {
        "sql": sql,
        "python": python,
        "notice": "Natija faqat tekshirish uchun tavsiya/indikator. Hukm emas va audit o'rnini bosmaydi.",
        "template": template,
    }
