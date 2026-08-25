export const STARTER_TEMPLATE = `<html>
<head>
<style>
  body { font-family: Helvetica, Arial, sans-serif; font-size: 12px; color: #1e293b; }
  header { display: flex; align-items: center; gap: 12px; border-bottom: 2px solid #1e293b; padding-bottom: 8px; margin-bottom: 12px; }
  header img { height: 48px; }
  h1 { font-size: 16px; margin: 0; }
  h2 { font-size: 13px; margin: 4px 0 12px; color: #475569; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  th, td { border: 1px solid #cbd5e1; padding: 4px 8px; text-align: left; }
  th { background: #f1f5f9; }
  .summary { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
  .qr { text-align: right; }
  .qr img { width: 70px; height: 70px; }
</style>
</head>
<body>
  <header>
    {% if school.logo_data_uri %}<img src="{{ school.logo_data_uri }}" alt="Logo" />{% endif %}
    <div>
      <h1>{{ school.name }}</h1>
      <h2>Bulletin — {{ academic_term.name }}</h2>
    </div>
  </header>

  <p>
    <strong>{{ student.last_name }} {{ student.first_name }}</strong> ({{ student.matricule }}) —
    Classe {{ school_class.name }}
  </p>

  <table>
    <tr>
      <th>Matière</th>
      <th>Coefficient</th>
      <th>Moyenne</th>
      <th>Rang</th>
      <th>Appréciation</th>
    </tr>
    {% for s in subjects %}
    <tr>
      <td>{{ s.name }}</td>
      <td>{{ s.coefficient }}</td>
      <td>{{ s.average if s.average is not none else "—" }}</td>
      <td>{{ s.rank if s.rank is not none else "—" }}</td>
      <td>{{ s.appreciation or "" }}</td>
    </tr>
    {% endfor %}
  </table>

  <div class="summary">
    <p><strong>Moyenne générale :</strong> {{ general_average if general_average is not none else "—" }} —
       <strong>Rang :</strong> {{ general_rank if general_rank is not none else "—" }}</p>
    <div class="qr">
      <img src="{{ qr_code_data_uri }}" alt="QR de vérification" />
      <p>Vérifier ce bulletin</p>
    </div>
  </div>

  <p><em>Généré le {{ generated_at }}</em></p>
</body>
</html>
`;
