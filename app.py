from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
import os
from werkzeug.utils import secure_filename
import uuid
import tempfile
import numpy as np

app = Flask(__name__)
CORS(app, origins="*")

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

sessions = {}

def clean_nan_values(data):
    if isinstance(data, list):
        return [
            {
                k: None if pd.isna(v) else v
                for k, v in row.items()
            }
            for row in data
        ]
    return data

def read_csv_with_fallback(filepath):
    encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']

    for encoding in encodings:
        try:
            return pd.read_csv(filepath, encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "utf-8",
        b"",
        0,
        0,
        "Failed with all encodings"
    )

@app.route('/upload', methods=['POST'])
def upload_file():

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)

    session_id = str(uuid.uuid4())

    filepath = os.path.join(
        UPLOAD_FOLDER,
        f"{session_id}_{filename}"
    )

    file.save(filepath)

    try:

        if filename.lower().endswith('.csv'):
            df = read_csv_with_fallback(filepath)
        else:
            df = pd.read_excel(filepath)

        # Clean column names
        df.columns = [str(col).strip() for col in df.columns]

        # Store full data
        data = df.to_dict('records')
        clean_data = clean_nan_values(data)

        # FULL DROPDOWN VALUES
        filter_columns = ["Industry", "Role", "Department"]

        filter_options = {}

        for col in filter_columns:

            if col in df.columns:

                values = (
                    df[col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .replace("", np.nan)
                    .dropna()
                    .unique()
                    .tolist()
                )

                values = sorted(values)

                filter_options[col] = values[:1000]

        sessions[session_id] = {
            'df': df,
            'data': clean_data,
            'columns': list(df.columns)
        }

        return jsonify({
            "success": True,
            "session_id": session_id,
            "columns": list(df.columns),
            "total_rows": len(data),
            "preview": clean_data[:100],
            "filter_options": filter_options
        })

    except Exception as e:
        return jsonify({
            "error": f"Failed to process file: {str(e)}"
        }), 500


@app.route('/filter', methods=['POST'])
def apply_filter():

    data = request.json

    session_id = data.get('session_id')

    if session_id not in sessions:
        return jsonify({
            "error": "Session expired. Please upload again."
        }), 400

    df = sessions[session_id]['df'].copy()

    filters = data.get('filters', {})
    text_searches = data.get('text_searches', {})
    search_term = data.get('search', '').lower().strip()

    # DROPDOWN FILTERS
    for col, values in filters.items():

        if values and len(values) > 0:

            values = [
                str(v).strip().lower()
                for v in values
            ]

            df = df[
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(values)
            ]

    # TEXT SEARCHES
    for col, term in text_searches.items():

        if term and term.strip():

            df = df[
                df[col]
                .astype(str)
                .str.contains(
                    term.strip(),
                    case=False,
                    na=False
                )
            ]

    # GLOBAL SEARCH
    if search_term:

        mask = pd.Series(False, index=df.index)

        for col in df.columns:

            mask |= (
                df[col]
                .astype(str)
                .str.lower()
                .str.contains(search_term, na=False)
            )

        df = df[mask]

    filtered_data = df.to_dict('records')

    clean_filtered = clean_nan_values(filtered_data)

    return jsonify({
        "total": len(clean_filtered),
        "data": clean_filtered[:1000]
    })


@app.route('/export', methods=['POST'])
def export_filtered():

    data = request.json

    session_id = data.get('session_id')

    filters = data.get('filters', {})
    text_searches = data.get('text_searches', {})

    if session_id not in sessions:
        return jsonify({
            "error": "Session expired"
        }), 400

    df = sessions[session_id]['df'].copy()

    # DROPDOWN FILTERS
    for col, values in filters.items():

        if values and len(values) > 0:

            values = [
                str(v).strip().lower()
                for v in values
            ]

            df = df[
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(values)
            ]

    # TEXT SEARCHES
    for col, term in text_searches.items():

        if term and term.strip():

            df = df[
                df[col]
                .astype(str)
                .str.contains(
                    term.strip(),
                    case=False,
                    na=False
                )
            ]

    df = df.replace({np.nan: None})

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix='.xlsx'
    )

    df.to_excel(temp_file.name, index=False)

    temp_file.close()

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name="Filtered_Candidates.xlsx"
    )


if __name__ == '__main__':
    print("🚀 RecruitFlow Backend Started at http://localhost:5000")
    app.run(debug=True, port=5000)