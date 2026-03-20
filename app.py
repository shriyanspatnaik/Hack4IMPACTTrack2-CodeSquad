from flask import Flask, render_template, request, jsonify
import sqlite3
import json
import os
from datetime import datetime
import anthropic
import re

app = Flask(__name__, static_folder='Static', static_url_path='/static')
app.secret_key = 'kritiquebuddy_secret_2024'


def init_db():
    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS patients
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL, phone TEXT NOT NULL,
                  age INTEGER, gender TEXT, symptoms TEXT,
                  bp TEXT, oxygen TEXT, sugar TEXT,
                  severity TEXT, severity_score INTEGER,
                  disease_predictions TEXT, progression_warning TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  status TEXT DEFAULT 'waiting')''')
    c.execute('''CREATE TABLE IF NOT EXISTS prescriptions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  patient_id INTEGER, medicines TEXT,
                  notes TEXT, follow_up TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS doctor_notes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  patient_id INTEGER, note TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()


init_db()


@app.route('/')
def index():
    return render_template('login.html')


@app.route('/assistant')
def assistant():
    return render_template('assistant.html')


@app.route('/doctor')
def doctor():
    conn = sqlite3.connect('kritiquebuddy.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'SELECT * FROM patients WHERE status="waiting" ORDER BY severity_score ASC, timestamp ASC')
    patients = [dict(row) for row in c.fetchall()]
    for p in patients:
        if p['disease_predictions']:
            p['disease_predictions'] = json.loads(p['disease_predictions'])
    c.execute('SELECT COUNT(*) FROM patients WHERE status="waiting"')
    total = c.fetchone()[0]
    c.execute(
        'SELECT COUNT(*) FROM patients WHERE severity="Critical" AND status="waiting"')
    critical = c.fetchone()[0]
    c.execute(
        'SELECT COUNT(*) FROM patients WHERE severity="Orange" AND status="waiting"')
    orange = c.fetchone()[0]
    c.execute(
        'SELECT COUNT(*) FROM patients WHERE severity="Moderate" AND status="waiting"')
    moderate = c.fetchone()[0]
    c.execute(
        'SELECT COUNT(*) FROM patients WHERE severity="Mild" AND status="waiting"')
    mild = c.fetchone()[0]
    conn.close()
    stats = {'total': total, 'critical': critical,
             'orange': orange, 'moderate': moderate, 'mild': mild}
    return render_template('doctor.html', patients=patients, stats=stats)


@app.route('/patient', methods=['GET', 'POST'])
def patient():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        lang = request.form.get('lang', 'en')
        conn = sqlite3.connect('kritiquebuddy.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''SELECT p.*, pr.medicines, pr.notes as presc_notes, pr.follow_up
                     FROM patients p LEFT JOIN prescriptions pr ON p.id = pr.patient_id
                     WHERE p.name=? AND p.phone=? ORDER BY p.timestamp DESC LIMIT 1''', (name, phone))
        pat = c.fetchone()
        conn.close()
        if pat:
            pat = dict(pat)
            if pat['disease_predictions']:
                pat['disease_predictions'] = json.loads(
                    pat['disease_predictions'])
            if pat.get('medicines'):
                pat['medicines'] = json.loads(pat['medicines'])
            return render_template('patient.html', patient=pat, lang=lang)
        return render_template('patient.html', error="No record found. Please check your details.", lang=lang)
    return render_template('patient.html')


@app.route('/api/add_patient', methods=['POST'])
def add_patient():
    data = request.json
    analysis = analyze_with_claude(data)
    severity_scores = {'Critical': 1, 'Orange': 2, 'Moderate': 3, 'Mild': 4}
    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
    c.execute('''INSERT INTO patients (name, phone, age, gender, symptoms, bp, oxygen, sugar,
                 severity, severity_score, disease_predictions, progression_warning)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (data['name'], data['phone'], data['age'], data['gender'],
               data['symptoms'], data['bp'], data['oxygen'], data['sugar'],
               analysis['severity'], severity_scores.get(
                   analysis['severity'], 4),
               json.dumps(analysis['diseases']), analysis['progression_warning']))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'analysis': analysis})


@app.route('/api/prescribe', methods=['POST'])
def prescribe():
    data = request.json
    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
    c.execute('INSERT INTO prescriptions (patient_id, medicines, notes, follow_up) VALUES (?, ?, ?, ?)',
              (data['patient_id'], json.dumps(data['medicines']), data.get('notes', ''), data.get('follow_up', '')))
    c.execute('UPDATE patients SET status="seen" WHERE id=?',
              (data['patient_id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/save_note', methods=['POST'])
def save_note():
    data = request.json
    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
    c.execute('INSERT INTO doctor_notes (patient_id, note) VALUES (?, ?)',
              (data['patient_id'], data['note']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/get_notes/<int:patient_id>')
def get_notes(patient_id):
    conn = sqlite3.connect('kritiquebuddy.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'SELECT * FROM doctor_notes WHERE patient_id=? ORDER BY timestamp DESC', (patient_id,))
    notes = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(notes)


def analyze_with_claude(patient_data):
    try:
        client = anthropic.Anthropic(
            api_key=os.environ.get('ANTHROPIC_API_KEY', ''))
        prompt = f"""You are a medical triage AI. Analyze this patient and respond ONLY in valid JSON.

Severity levels:
- Critical: Immediate life threat
- Orange: Will worsen rapidly if untreated (e.g. early dengue, appendicitis)
- Moderate: Needs attention, currently stable
- Mild: Minor condition

Patient:
- Age: {patient_data['age']}, Gender: {patient_data['gender']}
- Symptoms: {patient_data['symptoms']}
- BP: {patient_data['bp']}, Oxygen: {patient_data['oxygen']}%, Sugar: {patient_data['sugar']} mg/dL

Respond ONLY with this JSON (no extra text):
{{
  "severity": "Critical/Orange/Moderate/Mild",
  "diseases": [
    {{"name": "Disease 1", "likelihood": 60}},
    {{"name": "Disease 2", "likelihood": 25}},
    {{"name": "Disease 3", "likelihood": 15}}
  ],
  "progression_warning": "One sentence about how this worsens if untreated."
}}"""
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"Claude API error: {e}")
    return {
        "severity": "Moderate",
        "diseases": [
            {"name": "Viral Infection", "likelihood": 60},
            {"name": "General Illness", "likelihood": 25},
            {"name": "Other", "likelihood": 15}
        ],
        "progression_warning": "Please consult doctor immediately for proper diagnosis."
    }


if __name__ == '__main__':
    app.run(debug=True)
