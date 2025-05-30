from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os
import base64
import numpy as np
from PIL import Image
import io
import face_recognition
import json
import csv
from io import StringIO
from flask import make_response
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from io import BytesIO
import pytz

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://attendance_management_sd9w_user:jR6W58aVLDt11Werx7bJuQjaFNgGGhWW@dpg-d0snkn3uibrs73ajv0ig-a.virginia-postgres.render.com/attendance_management_sd9w'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(50), unique=True)
    email = db.Column(db.String(120))
    face_encoding = db.Column(db.Text)  
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendance_records = db.relationship('AttendanceRecord', backref='student', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Student {self.name}>'

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='present')
    confidence_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AttendanceRecord {self.student.name} - {self.date}>'

def process_image_data(image_data):
    try:
        print(f"Processing image data... Length: {len(image_data) if image_data else 0}")

        if not image_data:
            print("No image data provided")
            return None

        if image_data.startswith('data:image'):
            if ',' in image_data:
                image_data = image_data.split(',', 1)[1]
            else:
                print("Invalid data URL format")
                return None

        try:
            image_bytes = base64.b64decode(image_data)
            print(f"Decoded image bytes length: {len(image_bytes)}")
        except Exception as e:
            print(f"Base64 decode error: {e}")
            return None

        try:
            image = Image.open(io.BytesIO(image_bytes))
            print(f"Image opened successfully: {image.size}, Mode: {image.mode}")
        except Exception as e:
            print(f"PIL Image open error: {e}")
            return None

        if image.mode != 'RGB':
            image = image.convert('RGB')
            print("Converted image to RGB")

        return image

    except Exception as e:
        print(f"Error processing image: {e}")
        return None

def get_face_encoding(image):
    try:
        if image is None:
            print("No image provided to get_face_encoding")
            return None

        image_array = np.array(image)
        print(f"Image array shape: {image_array.shape}")

        face_locations = face_recognition.face_locations(image_array, model="hog")
        print(f"Found {len(face_locations)} face(s)")

        if not face_locations:

            try:
                face_locations = face_recognition.face_locations(image_array, model="cnn")
                print(f"CNN model found {len(face_locations)} face(s)")
            except:
                print("CNN model not available, using HOG results")

        if not face_locations:
            print("No faces detected in image")
            return None

        face_encodings = face_recognition.face_encodings(image_array, face_locations)
        print(f"Generated {len(face_encodings)} face encoding(s)")

        if face_encodings:
            return face_encodings[0]  

        print("No face encodings generated")
        return None

    except Exception as e:
        print(f"Error getting face encoding: {e}")
        return None

def find_matching_student(face_encoding, tolerance=0.6):
    try:
        if face_encoding is None:
            print("No face encoding provided for matching")
            return None, 0

        students = Student.query.all()
        print(f"Checking against {len(students)} students")

        best_match = None
        best_confidence = 0

        for student in students:
            if not student.face_encoding:
                continue

            try:

                stored_encoding = json.loads(student.face_encoding)
                stored_encoding = np.array(stored_encoding)

                distance = face_recognition.face_distance([stored_encoding], face_encoding)[0]
                confidence = 1 - distance

                print(f"Student: {student.name}, Distance: {distance:.3f}, Confidence: {confidence:.3f}")

                if distance <= tolerance and confidence > best_confidence:
                    best_match = student
                    best_confidence = confidence

            except Exception as e:
                print(f"Error processing student {student.name}: {e}")
                continue

        if best_match:
            print(f"Best match: {best_match.name} with confidence {best_confidence:.3f}")
            return best_match, best_confidence

        print("No matching student found")
        return None, 0

    except Exception as e:
        print(f"Error finding matching student: {e}")
        return None, 0

@app.route('/')
def index():
    try:
        total_students = Student.query.count()
        today_attendance = AttendanceRecord.query.filter_by(date=date.today()).count()

        return render_template('index.html', 
                             total_students=total_students,
                             today_attendance=today_attendance)
    except Exception as e:
        print(f"Index route error: {e}")
        return render_template('index.html', total_students=0, today_attendance=0)

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register_student():
    try:
        name = request.form.get('name', '').strip()
        student_id = request.form.get('student_id', '').strip()
        email = request.form.get('email', '').strip()
        face_data = request.form.get('face_data', '')

        print(f"Registration attempt for: {name}")

        if not name:
            flash('Student name is required', 'error')
            return redirect(url_for('register_page'))

        if not face_data:
            flash('Face capture is required for registration', 'error')
            return redirect(url_for('register_page'))

        if student_id and Student.query.filter_by(student_id=student_id).first():
            flash('Student ID already exists', 'error')
            return redirect(url_for('register_page'))

        image = process_image_data(face_data)
        if not image:
            flash('Invalid image data. Please try capturing your face again.', 'error')
            return redirect(url_for('register_page'))

        face_encoding = get_face_encoding(image)
        if face_encoding is None:
            flash('No face detected in the image. Please ensure your face is clearly visible and try again.', 'error')
            return redirect(url_for('register_page'))

        face_encoding_str = json.dumps(face_encoding.tolist())
        existing_student, confidence = find_matching_student(face_encoding, tolerance=0.5)

        if existing_student and confidence > 0.7:
            flash(f'Face already registered for student: {existing_student.name}', 'error')
            return redirect(url_for('register_page'))

        student = Student(
            name=name,
            student_id=student_id if student_id else None,
            email=email if email else None,
            face_encoding=face_encoding_str
        )

        db.session.add(student)
        db.session.commit()

        print(f"Student {name} registered successfully!")
        flash(f'Student {name} registered successfully!', 'success')
        return redirect(url_for('students_list'))

    except Exception as e:
        db.session.rollback()
        print(f"Registration error: {e}")
        flash('An error occurred during registration. Please try again.', 'error')
        return redirect(url_for('register_page'))

@app.route('/attendance')
def attendance_page():
    return render_template('attendance.html')

@app.route('/submit-attendance', methods=['POST'])
def submit_attendance():
    try:
        image_data = request.form.get('image_data', '')

        print("Attendance submission attempt")

        if not image_data:
            flash('No image data received', 'error')
            return redirect(url_for('attendance_page'))

        image = process_image_data(image_data)
        if not image:
            flash('Invalid image data. Please try again.', 'error')
            return redirect(url_for('attendance_page'))

        face_encoding = get_face_encoding(image)
        if face_encoding is None:
            flash('No face detected in the image. Please ensure your face is clearly visible and try again.', 'error')
            return redirect(url_for('attendance_page'))

        student, confidence = find_matching_student(face_encoding)

        if not student:
            flash('Face not recognized. Please register first or try again with better lighting.', 'error')
            return redirect(url_for('attendance_page'))

        if confidence < 0.4:
            flash('Face recognition confidence too low. Please try again with better lighting.', 'warning')
            return redirect(url_for('attendance_page'))

        today = date.today()
        existing_record = AttendanceRecord.query.filter_by(
            student_id=student.id,
            date=today
        ).first()

        if existing_record:
            flash(f'Attendance already recorded for {student.name} today at {existing_record.time.astimezone(pytz.timezone(\'Asia/Kolkata\')).strftime("%I:%M:%S %p")}.', 'warning')
            return redirect(url_for('attendance_page'))

        ist = pytz.timezone('Asia/Kolkata')
        attendance_time = datetime.now(ist)
        
        attendance = AttendanceRecord(
            student_id=student.id,
            confidence_score=confidence,
            status='present',
            time=attendance_time,
            date=today
        )

        db.session.add(attendance)
        db.session.commit()

        print(f"Attendance recorded for {student.name}")
        flash(f'Attendance recorded for {student.name} (Confidence: {confidence:.1%})', 'success')
        return redirect(url_for('attendance_reports'))

    except Exception as e:
        db.session.rollback()
        print(f"Attendance error: {e}")
        flash('An error occurred while recording attendance. Please try again.', 'error')
        return redirect(url_for('attendance_page'))

@app.route('/students')
def students_list():
    try:
        students = Student.query.order_by(Student.created_at.desc()).all()
        return render_template('students.html', students=students)
    except Exception as e:
        print(f"Students list error: {e}")
        flash('Error loading students list', 'error')
        return render_template('students.html', students=[])

@app.route('/reports')
def attendance_reports():
    try:
        today = date.today()

        today_records = db.session.query(AttendanceRecord, Student).join(Student).filter(
            AttendanceRecord.date == today,
        ).order_by(AttendanceRecord.time.desc()).all()

        all_students = Student.query.all()

        present_student_ids = [student.id for record, student in today_records]

        absent_students = [student for student in all_students 
                          if student.id not in present_student_ids]

        total_students = len(all_students)
        present_today = len(today_records)
        absent_today = len(absent_students)

        return render_template('reports.html', 
                             today_records=today_records,
                             absent_students=absent_students,
                             total_students=total_students,
                             present_today=present_today,
                             absent_today=absent_today,
                             today=today)
    except Exception as e:
        print(f"Reports error: {e}")
        flash('Error loading reports', 'error')
        return render_template('reports.html', 
                             today_records=[], absent_students=[],
                             total_students=0, present_today=0, absent_today=0,
                             today=date.today())

@app.route('/api/students')
def api_students():
    try:
        students = Student.query.all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'student_id': s.student_id,
            'email': s.email,
            'created_at': s.created_at.isoformat()
        } for s in students])
    except Exception as e:
        print(f"API students error: {e}")
        return jsonify({'error': 'Failed to fetch students'}), 500
@app.route('/api/students/<int:id>')
def api_students_filter(id):
    try:
        s = Student.query.get_or_404(id)
        return jsonify({
            'id': s.id,
            'name': s.name,
            'student_id': s.student_id,
            'email': s.email,
            'created_at': s.created_at.isoformat()
        } )
    except Exception as e:
        print(f"API students error: {e}")
        return jsonify({'error': 'Failed to fetch students'}), 500

@app.route('/api/attendance/<date_str>')
def api_attendance(date_str):
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        records = db.session.query(AttendanceRecord, Student).join(Student).filter(
            AttendanceRecord.date == target_date,
        ).all()

        return jsonify([{
            'student_name': student.name,
            'student_id': student.student_id,
            'time': record.time.isoformat() if record.time else None,
            'status': record.status,
            'confidence': record.confidence_score
        } for record, student in records])
    except ValueError as e:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    except Exception as e:
        print(f"API attendance error: {e}")
        return jsonify({'error': 'Failed to fetch attendance'}), 500

@app.route('/delete-student/<int:student_id>')
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash(f'Student {student.name} has been removed.', 'success')
    return redirect(url_for("students_list"))

@app.route('/api/students/<int:student_id>', methods=['PUT'])
def update_student(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json()

    student.name = data.get('name', student.name)
    student.student_id = data.get('student_id', student.student_id)
    student.email = data.get('email', student.email)

    db.session.commit()
    return redirect(url_for("students_list"))

@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    try:

        report_type = request.form.get('report_type', 'all_students')
        from_date_str = request.form.get('from_date')
        to_date_str = request.form.get('to_date')
        include_absent = request.form.get('include_absent', 'no')
        selected_student_ids = request.form.getlist('selected_students')

        if not from_date_str or not to_date_str:
            flash('Please select both from and to dates', 'error')
            return redirect(url_for('download_reports_page'))

        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()

        if from_date > to_date:
            flash('From date cannot be later than to date', 'error')
            return redirect(url_for('download_reports_page'))

        if report_type == 'selected_students':
            if not selected_student_ids:
                flash('Please select at least one student', 'error')
                return redirect(url_for('download_reports_page'))

            students_query = Student.query.filter(Student.id.in_(selected_student_ids))
        else:
            students_query = Student.query

        students = students_query.all()

        attendance_query = db.session.query(AttendanceRecord, Student).join(Student).filter(
            AttendanceRecord.date >= from_date,
            AttendanceRecord.date <= to_date
        )

        if report_type == 'selected_students':
            attendance_query = attendance_query.filter(Student.id.in_(selected_student_ids))

        attendance_records = attendance_query.order_by(
            AttendanceRecord.date.desc(),
            AttendanceRecord.time.desc()
        ).all()

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        title = Paragraph("Attendance Report", styles['Title'])
        story.append(title)

        details = f"From Date: {from_date_str} To Date: {to_date_str}"
        story.append(Paragraph(details, styles['Normal']))

        data = [['Date', 'Student Name', 'Student ID', 'Email', 'Time', 'Status', 'Confidence Score']]

        if include_absent == 'yes':

            current_date = from_date
            while current_date <= to_date:
                present_student_ids_today = [student.id for record, student in attendance_records if record.date == current_date]

                for record, student in attendance_records:
                    if record.date == current_date:
                        data.append([
                            record.date.strftime('%Y-%m-%d'),
                            student.name,
                            student.student_id or 'N/A',
                            student.email or 'N/A',
                            record.time.strftime('%H:%M:%S') if record.time else 'N/A',
                            'Present',
                            f"{record.confidence_score:.2%}" if record.confidence_score else 'N/A'
                        ])

                for student in students:
                    if student.id not in present_student_ids_today:
                        data.append([
                            current_date.strftime('%Y-%m-%d'),
                            student.name,
                            student.student_id or 'N/A',
                            student.email or 'N/A',
                            'N/A',
                            'Absent',
                            'N/A'
                        ])

                current_date += timedelta(days=1)
        else:

            for record, student in attendance_records:
                data.append([
                    record.date.strftime('%Y-%m-%d'),
                    student.name,
                    student.student_id or 'N/A',
                    student.email or 'N/A',
                    record.time.strftime('%H:%M:%S') if record.time else 'N/A',
                    record.status.title(),
                    f"{record.confidence_score:.2%}" if record.confidence_score else 'N/A'
                ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        story.append(table)
        doc.build(story)

        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_report_{from_date_str}_to_{to_date_str}.pdf'

        return response

    except Exception as e:
        print(f"PDF download error: {e}")
        flash('An error occurred while generating the report. Please try again.', 'error')
        return redirect(url_for('download_reports_page'))

@app.route("/reports_pdf")
def reports_pdf():
    try:
        students = Student.query.order_by(Student.name).all()

        default_to_date = date.today()
        default_from_date = default_to_date - timedelta(days=30)

        return render_template('download_pdf.html', 
                             students=students,
                             default_from_date=default_from_date.strftime('%Y-%m-%d'),
                             default_to_date=default_to_date.strftime('%Y-%m-%d'))
    except Exception as e:
        print(f"Download reports page error: {e}")
        flash('Error loading download page', 'error')
        return redirect(url_for('attendance_reports'))

@app.route('/download-reports')
def download_reports_page():
    try:
        students = Student.query.order_by(Student.name).all()

        default_to_date = date.today()
        default_from_date = default_to_date - timedelta(days=30)

        return render_template('download_reports.html', 
                             students=students,
                             default_from_date=default_from_date.strftime('%Y-%m-%d'),
                             default_to_date=default_to_date.strftime('%Y-%m-%d'))
    except Exception as e:
        print(f"Download reports page error: {e}")
        flash('Error loading download page', 'error')
        return redirect(url_for('attendance_reports'))

@app.route('/download-csv', methods=['POST'])
def download_csv():
    try:

        report_type = request.form.get('report_type', 'all_students')
        from_date_str = request.form.get('from_date')
        to_date_str = request.form.get('to_date')
        include_absent = request.form.get('include_absent', 'no')
        selected_student_ids = request.form.getlist('selected_students')

        if not from_date_str or not to_date_str:
            flash('Please select both from and to dates', 'error')
            return redirect(url_for('download_reports_page'))

        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()

        if from_date > to_date:
            flash('From date cannot be later than to date', 'error')
            return redirect(url_for('download_reports_page'))

        if report_type == 'selected_students':
            if not selected_student_ids:
                flash('Please select at least one student', 'error')
                return redirect(url_for('download_reports_page'))

            students_query = Student.query.filter(
                Student.id.in_(selected_student_ids)
            )
        else:
            students_query = Student.query.all()

        students = students_query.all()

        attendance_query = db.session.query(AttendanceRecord, Student).join(Student).filter(
            AttendanceRecord.date >= from_date,
            AttendanceRecord.date <= to_date
        )

        if report_type == 'selected_students':
            attendance_query = attendance_query.filter(Student.id.in_(selected_student_ids))

        attendance_records = attendance_query.order_by(
            AttendanceRecord.date.desc(), 
            AttendanceRecord.time.desc()
        ).all()

        output = StringIO()
        fieldnames = ['Date', 'Student Name', 'Student ID', 'Email', 'Time', 'Status', 'Confidence Score']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        if include_absent == 'yes':

            current_date = from_date
            while current_date <= to_date:

                present_student_ids_today = [
                    student.id for record, student in attendance_records 
                    if record.date == current_date
                ]

                for record, student in attendance_records:
                    if record.date == current_date:
                        writer.writerow({
                            'Date': record.date.strftime('%Y-%m-%d'),
                            'Student Name': student.name,
                            'Student ID': student.student_id or 'N/A',
                            'Email': student.email or 'N/A',
                            'Time': record.time.strftime('%H:%M:%S') if record.time else 'N/A',
                            'Status': 'Present',
                            'Confidence Score': f"{record.confidence_score:.2%}" if record.confidence_score else 'N/A'
                        })

                for student in students:
                    if student.id not in present_student_ids_today:
                        writer.writerow({
                            'Date': current_date.strftime('%Y-%m-%d'),
                            'Student Name': student.name,
                            'Student ID': student.student_id or 'N/A',
                            'Email': student.email or 'N/A',
                            'Time': 'N/A',
                            'Status': 'Absent',
                            'Confidence Score': 'N/A'
                        })

                current_date += timedelta(days=1)
        else:

            for record, student in attendance_records:
                writer.writerow({
                    'Date': record.date.strftime('%Y-%m-%d'),
                    'Student Name': student.name,
                    'Student ID': student.student_id or 'N/A',
                    'Email': student.email or 'N/A',
                    'Time': record.time.strftime('%H:%M:%S') if record.time else 'N/A',
                    'Status': record.status.title(),
                    'Confidence Score': f"{record.confidence_score:.2%}" if record.confidence_score else 'N/A'
                })

        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'

        filename = f"attendance_report_{from_date_str}_to_{to_date_str}.csv"
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'

        return response

    except Exception as e:
        print(f"CSV download error: {e}")
        flash('An error occurred while generating the report. Please try again.', 'error')
        return redirect(url_for('download_reports_page'))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('error.html', error='Internal server error'), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = 5000
    app.run(host='0.0.0.0', port=port)
