from flask import Flask, render_template, request, jsonify
import sqlite3
import json
import os
from datetime import datetime
import anthropic
import re

app = Flask(__name__, static_folder='Static', static_url_path='/static')
app.secret_key = 'kritiquebuddy_secret_2024'

DOCTORS = {
    'dr_anil':   {'name': 'Dr. Anil Sharma',    'spec': 'MBBS, MD — General Physician',  'room': 'Room 204', 'phone': '+91 98100 11111'},
    'dr_priya':  {'name': 'Dr. Priya Mehra',    'spec': 'MD, DM — Cardiologist',          'room': 'Room 301', 'phone': '+91 98100 22222'},
    'dr_rajan':  {'name': 'Dr. Rajan Verma',    'spec': 'MBBS, MD — Pulmonologist',       'room': 'Room 108', 'phone': '+91 98100 33333'},
    'dr_sunita': {'name': 'Dr. Sunita Rao',     'spec': 'MBBS, MD — Diabetologist',       'room': 'Room 212', 'phone': '+91 98100 44444'},
    'dr_karan':  {'name': 'Dr. Karan Malhotra', 'spec': 'MBBS, DNB — Emergency Medicine', 'room': 'Emergency Wing', 'phone': '+91 98100 55555'},
}


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
                  doctor_key TEXT, doctor_name TEXT, doctor_spec TEXT, doctor_room TEXT,
                  current_medications TEXT DEFAULT '',
                  known_conditions TEXT DEFAULT '',
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
    c.execute('''CREATE TABLE IF NOT EXISTS vitals_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  patient_id INTEGER NOT NULL,
                  bp TEXT, oxygen TEXT, sugar TEXT,
                  recorded_by TEXT DEFAULT 'Patient',
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    for col in ['current_medications', 'known_conditions']:
        try:
            c.execute(f'ALTER TABLE patients ADD COLUMN {col} TEXT DEFAULT ""')
        except:
            pass

    conn.commit()

    c.execute('SELECT COUNT(*) FROM patients')
    if c.fetchone()[0] == 0:
        mock_patients = [
            {
                'name': 'Priya Sharma', 'phone': '9876543201', 'age': 34, 'gender': 'Female',
                'symptoms': 'High fever 104°F for 2 days, severe headache, rash on arms and legs, joint pain',
                'bp': '90/60', 'oxygen': '96', 'sugar': '88',
                'severity': 'Critical', 'severity_score': 1,
                'diseases': [{'name': 'Dengue Fever', 'likelihood': 72}, {'name': 'Viral Fever', 'likelihood': 18}, {'name': 'Typhoid', 'likelihood': 10}],
                'warning': 'Platelet count may drop rapidly. Requires immediate hospitalization.',
                'doctor_key': 'dr_karan', 'doctor_name': 'Dr. Karan Malhotra', 'doctor_spec': 'MBBS, DNB — Emergency Medicine', 'doctor_room': 'Emergency Wing',
                'current_medications': 'None', 'known_conditions': 'No known allergies',
                'vitals_history': [('90/60', '96', '88'), ('92/62', '96', '90')]
            },
            {
                'name': 'Ramesh Gupta', 'phone': '9876543202', 'age': 58, 'gender': 'Male',
                'symptoms': 'Chest tightness, shortness of breath, mild left arm pain since morning, sweating',
                'bp': '150/95', 'oxygen': '94', 'sugar': '140',
                'severity': 'Orange', 'severity_score': 2,
                'diseases': [{'name': 'Angina / Cardiac Event', 'likelihood': 65}, {'name': 'Hypertension Crisis', 'likelihood': 25}, {'name': 'Anxiety Attack', 'likelihood': 10}],
                'warning': 'Possible cardiac event. Must be seen within 30 minutes to prevent serious complications.',
                'doctor_key': 'dr_priya', 'doctor_name': 'Dr. Priya Mehra', 'doctor_spec': 'MD, DM — Cardiologist', 'doctor_room': 'Room 301',
                'current_medications': 'Aspirin 75mg daily, Atorvastatin 20mg nightly',
                'known_conditions': 'Hypertension, Coronary Artery Disease',
                'vitals_history': [('160/100', '93', '130'), ('155/98', '94', '135'), ('150/95', '94', '140'), ('148/92', '95', '138')]
            },
            {
                'name': 'Sunita Patel', 'phone': '9876543203', 'age': 45, 'gender': 'Female',
                'symptoms': 'Persistent cough for 3 weeks, mild fever in evenings, night sweats, weight loss of 3kg',
                'bp': '118/76', 'oxygen': '97', 'sugar': '102',
                'severity': 'Moderate', 'severity_score': 3,
                'diseases': [{'name': 'Pulmonary Tuberculosis', 'likelihood': 55}, {'name': 'Chronic Bronchitis', 'likelihood': 30}, {'name': 'Pneumonia', 'likelihood': 15}],
                'warning': 'If TB is confirmed, isolation and immediate treatment required to prevent spread.',
                'doctor_key': 'dr_rajan', 'doctor_name': 'Dr. Rajan Verma', 'doctor_spec': 'MBBS, MD — Pulmonologist', 'doctor_room': 'Room 108',
                'current_medications': 'Salbutamol inhaler as needed',
                'known_conditions': 'Asthma (mild), No drug allergies',
                'vitals_history': [('120/78', '96', '100'), ('118/76', '97', '102'), ('116/74', '97', '100')]
            },
            {
                'name': 'Arun Kumar', 'phone': '9876543204', 'age': 62, 'gender': 'Male',
                'symptoms': 'Frequent urination, excessive thirst, blurred vision, fatigue for past month',
                'bp': '130/85', 'oxygen': '98', 'sugar': '320',
                'severity': 'Moderate', 'severity_score': 3,
                'diseases': [{'name': 'Uncontrolled Type 2 Diabetes', 'likelihood': 80}, {'name': 'Diabetic Neuropathy', 'likelihood': 12}, {'name': 'Hypertension', 'likelihood': 8}],
                'warning': 'Blood sugar dangerously high. Risk of diabetic ketoacidosis if untreated.',
                'doctor_key': 'dr_sunita', 'doctor_name': 'Dr. Sunita Rao', 'doctor_spec': 'MBBS, MD — Diabetologist', 'doctor_room': 'Room 212',
                'current_medications': 'Metformin 500mg twice daily, Insulin Glargine 10 units at bedtime',
                'known_conditions': 'Type 2 Diabetes (10 years), Hypertension, Penicillin allergy',
                'vitals_history': [('135/88', '97', '298'), ('128/82', '98', '310'), ('130/85', '98', '320'), ('125/80', '98', '305')]
            },
            {
                'name': 'Meera Joshi', 'phone': '9876543205', 'age': 28, 'gender': 'Female',
                'symptoms': 'Mild cold, runny nose, sore throat for 2 days, no fever',
                'bp': '110/70', 'oxygen': '99', 'sugar': '95',
                'severity': 'Mild', 'severity_score': 4,
                'diseases': [{'name': 'Common Cold', 'likelihood': 75}, {'name': 'Allergic Rhinitis', 'likelihood': 20}, {'name': 'Sinusitis', 'likelihood': 5}],
                'warning': 'Likely viral. Should resolve in 5-7 days with rest and hydration.',
                'doctor_key': 'dr_anil', 'doctor_name': 'Dr. Anil Sharma', 'doctor_spec': 'MBBS, MD — General Physician', 'doctor_room': 'Room 204',
                'current_medications': 'None',
                'known_conditions': 'No known conditions',
                'vitals_history': [('110/70', '99', '95'), ('112/72', '99', '96')]
            },
        ]

        for p in mock_patients:
            c.execute('''INSERT INTO patients (name, phone, age, gender, symptoms, bp, oxygen, sugar,
                         severity, severity_score, disease_predictions, progression_warning,
                         doctor_key, doctor_name, doctor_spec, doctor_room,
                         current_medications, known_conditions)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (p['name'], p['phone'], p['age'], p['gender'], p['symptoms'],
                       p['bp'], p['oxygen'], p['sugar'], p['severity'], p['severity_score'],
                       json.dumps(p['diseases']), p['warning'],
                       p['doctor_key'], p['doctor_name'], p['doctor_spec'], p['doctor_room'],
                       p['current_medications'], p['known_conditions']))
            conn.commit()
            c.execute('SELECT id FROM patients WHERE name=? AND phone=?',
                      (p['name'], p['phone']))
            pid = c.fetchone()[0]

            vitals = p.get('vitals_history', [])
            for i, vh in enumerate(vitals):
                if i == 0:
                    recorded_by = 'Initial Record (Doctor)'
                elif i == len(vitals) - 1:
                    recorded_by = 'Patient'
                else:
                    recorded_by = 'Doctor'
                c.execute('''INSERT INTO vitals_history (patient_id, bp, oxygen, sugar, recorded_by)
                             VALUES (?, ?, ?, ?, ?)''', (pid, vh[0], vh[1], vh[2], recorded_by))

        conn.commit()

        # Prescriptions for Meera and Arun
        c.execute('SELECT id FROM patients WHERE name="Meera Joshi"')
        meera = c.fetchone()
        if meera:
            c.execute('''INSERT INTO prescriptions (patient_id, medicines, notes, follow_up) VALUES (?, ?, ?, ?)''',
                      (meera[0], json.dumps([
                          {'name': 'Cetirizine', 'dose': '10mg',
                              'timing': 'Night', 'food': 'After meal'},
                          {'name': 'Paracetamol', 'dose': '500mg',
                              'timing': 'Morning & Night', 'food': 'After meal'},
                          {'name': 'Vitamin C', 'dose': '500mg',
                              'timing': 'Morning', 'food': 'With meal'}
                      ]), 'Rest well, drink warm fluids', '2026-03-27'))

        c.execute('SELECT id FROM patients WHERE name="Arun Kumar"')
        arun = c.fetchone()
        if arun:
            c.execute('''INSERT INTO prescriptions (patient_id, medicines, notes, follow_up) VALUES (?, ?, ?, ?)''',
                      (arun[0], json.dumps([
                          {'name': 'Metformin', 'dose': '500mg',
                              'timing': 'Morning & Night', 'food': 'After meal'},
                          {'name': 'Glipizide', 'dose': '5mg',
                              'timing': 'Morning', 'food': 'Before meal'},
                          {'name': 'Amlodipine', 'dose': '5mg',
                              'timing': 'Night', 'food': 'After meal'}
                      ]), 'Strict diet control. Avoid sugary foods.', '2026-03-28'))

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
                     WHERE p.name=? AND p.phone=? ORDER BY pr.timestamp DESC LIMIT 1''', (name, phone))
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
        return render_template('patient.html', error="No record found. Please check your name and phone number.", lang=lang)
    return render_template('patient.html')


@app.route('/api/add_patient', methods=['POST'])
def add_patient():
    data = request.json
    analysis = analyze_with_claude(data)
    severity_scores = {'Critical': 1, 'Orange': 2, 'Moderate': 3, 'Mild': 4}
    doctor_key = data.get('doctor_key', '')
    doctor_info = DOCTORS.get(doctor_key, {})

    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
    c.execute('''INSERT INTO patients (name, phone, age, gender, symptoms, bp, oxygen, sugar,
                 severity, severity_score, disease_predictions, progression_warning,
                 doctor_key, doctor_name, doctor_spec, doctor_room,
                 current_medications, known_conditions)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (data['name'], data['phone'], data['age'], data['gender'],
               data['symptoms'], data['bp'], data['oxygen'], data['sugar'],
               analysis['severity'], severity_scores.get(
                   analysis['severity'], 4),
               json.dumps(analysis['diseases']
                          ), analysis['progression_warning'],
               doctor_key, doctor_info.get(
                   'name', data.get('doctor_name', '')),
               doctor_info.get('spec', ''), doctor_info.get('room', ''),
               data.get('current_medications', ''), data.get('known_conditions', '')))
    patient_id = c.lastrowid

    bp = data.get('bp', '')
    oxygen = data.get('oxygen', '')
    sugar = data.get('sugar', '')
    if any(v and v != 'Not measured' for v in [bp, oxygen, sugar]):
        c.execute('''INSERT INTO vitals_history (patient_id, bp, oxygen, sugar, recorded_by) VALUES (?, ?, ?, ?, ?)''',
                  (patient_id,
                   bp if bp != 'Not measured' else None,
                   oxygen if oxygen != 'Not measured' else None,
                   sugar if sugar != 'Not measured' else None,
                   'Initial Record (Doctor)'))

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
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/mark_seen', methods=['POST'])
def mark_seen():
    data = request.json
    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
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


@app.route('/api/vitals_history/<int:patient_id>')
def vitals_history(patient_id):
    conn = sqlite3.connect('kritiquebuddy.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'SELECT * FROM vitals_history WHERE patient_id=? ORDER BY timestamp ASC', (patient_id,))
    records = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(records)


@app.route('/api/add_vital', methods=['POST'])
def add_vital():
    data = request.json
    conn = sqlite3.connect('kritiquebuddy.db')
    c = conn.cursor()
    bp = data.get('bp') or None
    oxygen = data.get('oxygen') or None
    sugar = data.get('sugar') or None
    recorded_by = data.get('recorded_by', 'Patient')
    c.execute('''INSERT INTO vitals_history (patient_id, bp, oxygen, sugar, recorded_by) VALUES (?, ?, ?, ?, ?)''',
              (data['patient_id'], bp, oxygen, sugar, recorded_by))
    if bp:
        c.execute('UPDATE patients SET bp=? WHERE id=?',
                  (bp, data['patient_id']))
    if oxygen:
        c.execute('UPDATE patients SET oxygen=? WHERE id=?',
                  (oxygen, data['patient_id']))
    if sugar:
        c.execute('UPDATE patients SET sugar=? WHERE id=?',
                  (sugar, data['patient_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


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
- Current Medications: {patient_data.get('current_medications', 'None')}
- Known Conditions / Allergies: {patient_data.get('known_conditions', 'None')}

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
