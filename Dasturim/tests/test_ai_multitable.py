import pandas as pd

from ai import ask_question, explain_python, explain_sql, generate_insights, suggest_cleaning_steps


def test_ask_question_supports_multi_table_join(monkeypatch):
    customers = pd.DataFrame({
        "id": [1, 2],
        "name": ["Ali", "Vali"],
    })
    orders = pd.DataFrame({
        "customer_id": [1, 1, 2],
        "amount": [10, 20, 30],
    })

    def fake_call_model(system, user):
        assert 'Jadval "customers"' in user or 'Jadval "orders"' in user
        return (
            '{"sql": "SELECT c.name, SUM(o.amount) AS total FROM customers c ' 
            'JOIN orders o ON o.customer_id = c.id GROUP BY c.name ORDER BY total DESC", '
            '"explanation": "Har bir mijoz uchun buyurtmalar summasini biriktirib, eng katta qiymatga ega mijozni aniqladim."}'
        )

    monkeypatch.setattr("ai.call_model", fake_call_model)

    result = ask_question(
        customers,
        "Qaysi mijoz eng ko'p pul sarfladi?",
        {"customers": customers, "orders": orders},
    )

    assert result["sql"].upper().count("JOIN") == 1
    assert result["columns"] == ["name", "total"]
    assert result["rows"][0][1] == 30
    assert result["rows"][0][0] in {"Ali", "Vali"}
    assert "mijoz" in result["explanation"].lower() or "buyurtma" in result["explanation"].lower()


def test_explain_helpers_return_stepwise_uzbek_guidance(monkeypatch):
    data = pd.DataFrame({"id": [1, 2], "value": [10, 20]})

    def fake_call_model(system, user):
        if "Python kodi" in user:
            return '{"explanation": "1-qadam: qiymatlarni birlashtiramiz. 2-qadam: yig\'indini chiqaramiz.", "fixed_code": "print(df[\\"value\\"].sum())"}'
        return '{"explanation": "1-qadam: jadvalni tanlaymiz. 2-qadam: shartni qo\'yamiz. 3-qadam: natijani chiqaramiz.", "fixed_sql": "SELECT id, value FROM data WHERE value > 0"}'

    monkeypatch.setattr("ai.call_model", fake_call_model)

    sql_explained = explain_sql("SELECT * FROM data WHERE value > 0", {"data": data})
    py_explained = explain_python("print(df['value'].sum())")

    assert "qadam" in sql_explained["explanation"].lower()
    assert sql_explained["sql"].startswith("SELECT")
    assert py_explained["code"].startswith("print(")


def test_cleaning_suggestions_are_structured(monkeypatch):
    frame = pd.DataFrame({
        "customer": [" Ali ", "Vali", "Ali", ""],
        "amount": ["10", "x", "20", "30"],
    })

    def fake_call_model(system, user):
        return '{"steps": [{"type": "trim_text", "column": "customer", "reason": "Nomlarda ortiqcha bo\'sh joylar bor."}, {"type": "convert_number", "column": "amount", "reason": "Raqamli ustunni to\'g\'rilash kerak."}]}'

    monkeypatch.setattr("ai.call_model", fake_call_model)

    result = suggest_cleaning_steps(frame)
    assert result["steps"][0]["type"] == "trim_text"
    assert result["steps"][1]["column"] == "amount"


def test_generate_insights_labels_hypotheses_and_sql(monkeypatch):
    frame = pd.DataFrame({
        "region": ["A", "A", "B", "B", "C"],
        "sales": [10, 12, 15, 100, 14],
    })

    def fake_call_model(system, user):
        return '{"insights": [{"label": "FARAZ", "type": "trend", "title": "Boshqa hududlar bilan solishtirish", "description": "A hududining savdosi boshqasiga nisbatan yuqori bo\'lishi mumkin.", "sql": "SELECT region, AVG(sales) AS avg_sales FROM data GROUP BY region ORDER BY avg_sales DESC"}]}'

    monkeypatch.setattr("ai.call_model", fake_call_model)

    result = generate_insights(frame, {"data": frame}, limit=2)
    assert result[0]["label"] == "FARAZ"
    assert result[0]["type"] == "trend"
    assert result[0]["sql"].upper().startswith("SELECT")
