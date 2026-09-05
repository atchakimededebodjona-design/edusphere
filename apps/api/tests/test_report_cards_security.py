"""Tests de sécurité dédiés — correction SSTI (Phase 7.2).

`report_cards/service.py::render_template` rend le `html_content` d'un `ReportCardTemplate`
(entièrement contrôlé par SCHOOL_ADMIN/DIRECTOR via `POST /report-card-templates`) avec Jinja2.
Avant Phase 7.2, l'environnement Jinja2 n'était pas sandboxé : une expression comme
`{{ ''.__class__.__mro__[1].__subclasses__() }}` donnait accès à l'intégralité du graphe
d'objets Python (fichiers, variables d'environnement, secrets) depuis un compte d'école tout à
fait normal — confirmé par une preuve de concept non destructive avant correction.

Tests unitaires (3-6) : ciblent directement `render_template`, le point exact de la faille,
plutôt que de dupliquer les scénarios déjà couverts par `test_report_cards.py`.
Tests d'intégration (1/2/7/8) : confirment qu'un template légitime produit toujours un bulletin
exploitable de bout en bout, et que l'isolation tenant n'a pas régressé.
"""

from datetime import date

import pytest
from httpx import AsyncClient
from jinja2.exceptions import SecurityError

from app.modules.report_cards.service import render_template
from tests.conftest import register_school

MINIMAL_TEMPLATE = """
<html><body>
<h1>{{ school.name }}</h1>
<h2>Bulletin - {{ academic_term.name }}</h2>
<p>{{ student.first_name }} {{ student.last_name }} ({{ student.matricule }}) - Classe {{ school_class.name }}</p>
<table>
<tr><th>Matiere</th><th>Coef</th><th>Moyenne</th><th>Rang</th></tr>
{% for s in subjects %}
<tr><td>{{ s.name }}</td><td>{{ s.coefficient }}</td><td>{{ s.average }}</td><td>{{ s.rank }}</td></tr>
{% endfor %}
</table>
<p>Moyenne generale: {{ general_average }} - Rang: {{ general_rank }}</p>
<img src="{{ qr_code_data_uri }}" width="80" />
</body></html>
"""


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _setup_graded_class(client: AsyncClient, headers: dict, school_id: str) -> dict:
    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": "2026-2027",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=headers,
        )
    ).json()
    term = (
        await client.post(
            "/api/v1/academic-terms",
            json={
                "academic_year_id": year["id"],
                "name": "Trimestre 1",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2026, 12, 20)),
            },
            headers=headers,
        )
    ).json()
    level = (await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": "CE1"}, headers=headers)).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers,
        )
    ).json()
    math = (await client.post("/api/v1/subjects", json={"school_id": school_id, "name": "Mathematiques"}, headers=headers)).json()
    math_cs = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": math["id"], "coefficient": 1},
            headers=headers,
        )
    ).json()
    assessment_type = (
        await client.post("/api/v1/assessment-types", json={"school_id": school_id, "name": "Devoir"}, headers=headers)
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": "SEC001",
                "first_name": "Ama",
                "last_name": "Koffi",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "F",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers,
    )
    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": math_cs["id"],
                "academic_term_id": term["id"],
                "assessment_type_id": assessment_type["id"],
                "name": "Devoir 1",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/results",
        json={"assessment_id": assessment["id"], "results": [{"student_id": student["id"], "score": 15}]},
        headers=headers,
    )
    return {"year": year, "term": term, "class": school_class, "student": student}


# --- 3-6 : tests unitaires directement sur render_template (le point exact de la faille) ------
def test_legitimate_expression_still_renders() -> None:
    """1/2 (partiel, niveau unitaire) — variable métier légitime : fonctionne normalement."""
    html = render_template("<p>{{ student.first_name }} a {{ note }}/20</p>", {"student": {"first_name": "Ama"}, "note": 15})
    assert html == "<p>Ama a 15/20</p>"


def test_arbitrary_jinja_expression_object_access_is_blocked() -> None:
    """3/4 — accès à un objet Python via les attributs dunder : refusé."""
    with pytest.raises(SecurityError):
        render_template("{{ ''.__class__.__mro__[1].__subclasses__() }}", {})


def test_globals_access_via_self_is_blocked() -> None:
    """4/5 — accès aux globals (chemin classique vers os/settings/secrets) : refusé."""
    with pytest.raises(SecurityError):
        render_template("{{ self.__init__.__globals__ }}", {})


def test_file_access_attempt_is_blocked() -> None:
    """6 — tentative d'accès à des fichiers via l'objet `open` atteint par le graphe d'objets :
    refusé au même point (accès dunder bloqué avant même d'atteindre `open`)."""
    with pytest.raises(SecurityError):
        render_template(
            "{{ ''.__class__.__base__.__subclasses__()[0].__init__.__globals__['__builtins__']['open']('/etc/passwd').read() }}",
            {},
        )


def test_attr_filter_bypass_attempt_does_not_leak_data() -> None:
    """Contournement connu du filtre `attr()` (évite l'accès direct par point) : ne lève pas
    forcément d'exception (Undefined silencieux, comportement standard Jinja2 hors contexte
    imprimé) mais ne renvoie jamais la valeur réelle de l'attribut dangereux."""
    result = render_template("{{ ''|attr('__class__') }}", {})
    assert "class" not in result.lower()
    assert result == ""


# --- 1/2/7 : bout en bout, template légitime — la fonctionnalité doit être préservée -----------
async def test_legitimate_template_generates_and_publishes_report_card(client: AsyncClient) -> None:
    data = await register_school(client, "sectemplateok")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    ctx = await _setup_graded_class(client, headers, school_id)

    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_id, "name": "Standard", "html_content": MINIMAL_TEMPLATE},
            headers=headers,
        )
    ).json()

    generate = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": template["id"]},
        headers=headers,
    )
    assert generate.status_code == 200, generate.text
    report_card = generate.json()[0]
    assert report_card["student_id"] == ctx["student"]["id"]

    publish = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=headers)
    assert publish.status_code == 200
    assert publish.json()["published_at"] is not None

    pdf = await client.get(f"/api/v1/report-cards/{report_card['id']}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"


async def test_malicious_template_generation_does_not_leak_data(client: AsyncClient) -> None:
    """Un template malveillant soumis via l'API réelle (pas seulement au niveau service) ne doit
    jamais aboutir à un bulletin exposant des données/objets internes. Le fixture `client` utilise
    `ASGITransport(raise_app_exceptions=True)` (défaut httpx, pratique de débogage en test) : une
    exception non gérée dans l'endpoint est relevée directement ici plutôt que convertie en 500 —
    en production (Uvicorn), Starlette la convertirait en 500 générique sans fuite (comportement
    vérifié séparément §Étape 8/9 du rapport). Dans les deux cas, le point vérifié est le même :
    le payload n'est JAMAIS exécuté avec succès, la génération échoue sûrement."""
    data = await register_school(client, "secmalicious")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    ctx = await _setup_graded_class(client, headers, school_id)

    malicious_template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={
                "school_id": school_id,
                "name": "Malveillant",
                "html_content": "<p>{{ ''.__class__.__mro__[1].__subclasses__() }}</p>",
            },
            headers=headers,
        )
    ).json()
    # La création du template elle-même n'est pas bloquée (le contenu métier autorisé d'un
    # template reste libre) — c'est le RENDU qui doit échouer sûrement, jamais réussir.
    assert malicious_template.get("id") is not None

    with pytest.raises(SecurityError):
        await client.post(
            "/api/v1/report-cards/generate",
            json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": malicious_template["id"]},
            headers=headers,
        )


# --- 8 : isolation tenant maintenue après la correction ----------------------------------------
async def test_tenant_isolation_maintained_after_fix(client: AsyncClient) -> None:
    school_a = await register_school(client, "secisoa")
    school_b = await register_school(client, "secisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    ctx_b = await _setup_graded_class(client, headers_b, school_b["school"]["id"])
    template_b = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_b["school"]["id"], "name": "Standard", "html_content": MINIMAL_TEMPLATE},
            headers=headers_b,
        )
    ).json()
    generate_b = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx_b["class"]["id"], "academic_term_id": ctx_b["term"]["id"], "template_id": template_b["id"]},
        headers=headers_b,
    )
    report_card_b = generate_b.json()[0]

    forged = await client.get(f"/api/v1/report-cards/{report_card_b['id']}", headers=headers_a)
    assert forged.status_code == 404
