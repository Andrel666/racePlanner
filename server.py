from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from waitress import serve
from simulateRunPlan import  simulate_training_plan, load_config, format_results
from datetime import datetime
import os

app = Flask(__name__)

"""
@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')
"""

UPLOAD_FOLDER = 'uploads'  # Folder where files will be stored

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def load_input_files():
    if request.method == 'POST':
        # Check if a file was uploaded
        if 'file_input' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['file_input']

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        # Check if it's a valid file (CSV or JSON)
        if file and (file.filename.endswith('.json') or file.filename.endswith('.csv')):
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)

            if file.filename.endswith('.json'):
                # Handle JSON file (config)
                flash(f'Config file "{file.filename}" uploaded successfully.')
            elif file.filename.endswith('.csv'):
                # Handle CSV file (historical runs)
                flash(f'Historical runs file "{file.filename}" uploaded successfully.')
        else:
            flash('Invalid file type. Please upload a JSON or CSV file.')
            return redirect(request.url)

        return render_template('index.html')


from datetime import datetime


def calculate_weeks_between(start_date_str, end_date_str):
    """
    Calculate the number of weeks between two dates.

    Args:
    start_date_str (str): The start date as a string in the format YYYY-MM-DD.
    end_date_str (str): The end date as a string in the format YYYY-MM-DD.

    Returns:
    int: The number of weeks between the two dates.
    """
    # Convert the string dates to datetime objects
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    # Calculate the difference in days and convert to weeks
    delta_days = (end_date - start_date).days
    return delta_days // 7



@app.route('/', methods=['GET', 'POST'])
def index():
    #load_input_files()
    config_filename = 'config.json'
    config = load_config(config_filename)
    if request.method == 'POST':
        try:

            # Create a dictionary object to hold all form inputs
            user_params = {
                'initial_atl': float(request.form['initial_atl']),
                'initial_ctl': float(request.form['initial_ctl']),
                'num_weeks': int(request.form['num_weeks']),
                'initial_long_run_duration': float(request.form['initial_long_run_duration']),
                'initial_tempo_run_duration': float(request.form['initial_tempo_run_duration']),
                'initial_long_run_pace': float(request.form['long_run_pace']),
                'initial_tempo_run_pace': float(request.form['tempo_run_pace']),
                'start_date': datetime.strptime(request.form['start_date'], '%Y-%m-%d'),
                'end_date': datetime.strptime(request.form['end_date'], '%Y-%m-%d')
            }
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            # Run the simulation using the dictionary object
            training_plan = generate_plan(user_params)
            training_plan, race_plan, total_time = format_results(training_plan, start_date)

            # Display the results
            return render_template('results.html', training_plan=training_plan, race_plan=race_plan , total_time=total_time)
        except Exception as e:
            return str(e)

    # Pre-fill the form with default values from config.json
    return render_template('index.html', config=config)

@app.route('/generate_plan', methods=['POST'])
def call_generate_plan():
    try:
        # Get the JSON data sent from the client
        data = request.get_json()
        if data['type'] == 'config':

            #data = data['data']
            data = data.get('config')
            # Create a dictionary object to hold all form inputs (with appropriate type casting)

            user_params = {
                'initial_atl': float(data.get('initial_atl', 0)),
                'initial_ctl': float(data.get('initial_ctl', 0)),
                'num_weeks': int(data.get('num_weeks', 0)),
                'long_run_duration': float(data.get('long_run_duration', 0)),
                'tempo_run_duration': float(data.get('tempo_run_duration', 0)),
                'long_run_pace': float(data.get('long_run_pace', 0)),
                'tempo_run_pace': float(data.get('tempo_run_pace', 0)),
                'start_date': datetime.strptime(data.get('start_date', '2024-01-01'), '%Y-%m-%d'),
                'end_date': datetime.strptime(data.get('end_date', '2024-01-01'), '%Y-%m-%d')
            }
            #user_params = data['data']

            # Run the simulation using the dictionary object
            #training_plan = generate_plan(user_params)
            training_plan = simulate_training_plan(user_params)

            # Format the results
            start_date = user_params['start_date']

        elif data['type'] == 'historical':
            csv_data = data.get('csv')
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            num_weeks = calculate_weeks_between(start_date, end_date)
            user_params = {
                'start_date': datetime.strptime(start_date, '%Y-%m-%d'),
                'end_date': datetime.strptime(end_date, '%Y-%m-%d'),
                'num_weeks': num_weeks
            }

            #training_plan = simulate_training_plan(historical_runs =data['data'] )
            training_plan = simulate_training_plan(config=user_params, historical_runs=csv_data)
            start_date = training_plan[0]['week_sunday']

        training_plan, race_plan, total_time = format_results(training_plan, start_date)

        return render_template('results.html', training_plan=training_plan, race_plan=race_plan, total_time=total_time)

    except Exception as e:
        # Return an error message to the client in case something goes wrong
        return jsonify({'error': str(e)}), 400

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)
