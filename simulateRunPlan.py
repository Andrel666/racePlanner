import json
import csv
import math
from io import StringIO


from datetime import datetime, timedelta

# Constants for ATL and CTL smoothing factors
ATL_DECAY = 1 - math.exp(-1 / 7)  # Approximate 7-day time constant
CTL_DECAY = 1 - math.exp(-1 / 42)  # Approximate 42-day time constant

# Constants from configuration
PROGRESSIVE_OVERLOAD = 1.1  # Example value, to be set from config
MAX_LONG_RUN_DURATION = 120  # Example value in minutes, to be set from config
MAX_TEMPO_RUN_DURATION = 90  # Example value in minutes, to be set from config
MAX_HEART_RATE = 200  # Example value, to be set from config
RESTING_HEART_RATE = 60  # Example value, to be set from config


# Function to update ATL, CTL, and TSB using TRIMP
def update_fitness_fatigue(atl, ctl, trimp):
    trimp_normalized = trimp / 100
    atl_new = atl * (1 - ATL_DECAY) + trimp_normalized * ATL_DECAY
    ctl_new = ctl * (1 - CTL_DECAY) + trimp_normalized * CTL_DECAY
    tsb_new = ctl_new - atl_new
    return atl_new, ctl_new, tsb_new


# Function to calculate the number of weeks between two dates
def calculate_num_weeks(start_date, end_date):
    if isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Invalid date format for start_date: {start_date}. Expected 'YYYY-MM-DD'.")

    if isinstance(end_date, str):
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Invalid date format for end_date: {end_date}. Expected 'YYYY-MM-DD'.")

    if start_date > end_date:
        raise ValueError("start_date must be earlier than end_date.")

    delta = end_date - start_date
    return (delta.days // 7) + 1  # Number of weeks


# Function to calculate distance based on pace and duration
def calculate_distance(duration_minutes, pace_minutes_per_km):
    return duration_minutes / pace_minutes_per_km


# Function to estimate TRIMP based on duration and average heart rate
def estimate_trimp(duration_minutes, avg_hr):
    hr_factor = (avg_hr - RESTING_HEART_RATE) / (MAX_HEART_RATE - RESTING_HEART_RATE)
    trimp = duration_minutes * hr_factor
    return trimp


# Function to estimate pace based on training load and power
def estimate_pace(last_pace, atl, ctl, trimp, avg_hr, power):
    return estimate_pace_trimp(last_pace, atl, ctl, trimp, avg_hr, power)


def estimate_pace_trimp(last_pace, atl, ctl, trimp, avg_hr, power):
    k1 = 0.1  # CTL sensitivity
    k2 = 0.1  # ATL sensitivity
    k3 = 0.05  # TRIMP sensitivity
    k5 = 0.02  # Power sensitivity
    k6 = 0.001  # Avg HR sensitivity

    ctl_scaled = ctl / 50
    atl_scaled = atl / 50
    trimp_scaled = trimp / 100

    estimated_pace = (last_pace -
                      k1 * ctl_scaled +
                      k2 * atl_scaled +
                      k3 * trimp_scaled -
                      k5 * (power / 100) -
                      k6 * (avg_hr - RESTING_HEART_RATE))

    return max(estimated_pace, last_pace * 0.75)


# Function to simulate the training week
def simulate_week(training_plan, atl, ctl):
    total_trimp = 0
    for session in training_plan:
        trimp = session.get('trimp')
        total_trimp += trimp
        atl, ctl, tsb = update_fitness_fatigue(atl, ctl, trimp)
    return atl, ctl, tsb, total_trimp


# Function to adjust durations for progressive overload and easier weeks
def adjust_duration(week_num, last_week_duration):
    # Check if last_week_duration is a string and convert to float
    if isinstance(last_week_duration, str):
        try:
            last_week_duration = float(last_week_duration)
        except ValueError:
            raise ValueError(
                f"Invalid value for last_week_duration: {last_week_duration}. It must be convertible to a float.")

    if week_num % 4 == 0:
        new_duration = last_week_duration * 0.7  # Reduce duration by 30% for an easier week
    else:
        new_duration = last_week_duration * PROGRESSIVE_OVERLOAD

        if ((week_num - 1) % 4 == 0) and (week_num != 1):
            new_duration = last_week_duration + (PROGRESSIVE_OVERLOAD / 2) * last_week_duration

    return new_duration


def calculate_fitness_from_history(historical_runs):
    total_trimp = 0
    atl = 0
    ctl = 0
    num_runs = len(historical_runs)

    #really bad numbers if none given
    last_run_pace = 10.0  # Default pace if no data
    last_long_run_pace = 10.0  # Default long run pace
    last_tempo_run_pace = 10.0  # Default tempo run pace
    last_long_run_duration = 10  # Default long run duration (in minutes)
    last_tempo_run_duration = 10  # Default tempo run duration (in minutes)

    # Loop through each historical run and update ATL and CTL
    for run in historical_runs:
        trimp = run['trimp']
        atl, ctl, _ = update_fitness_fatigue(atl, ctl, trimp)
        total_trimp += trimp

        # Check if the run type is 'long_run' and update long run data accordingly
        if run.get('run_type') == 'long_run':
            last_long_run_pace = run['pace']
            last_long_run_duration = run['duration']
        elif run.get('run_type') == 'tempo_run_1':
            last_tempo_run_pace = run['pace']
            last_tempo_run_duration = run['duration']

    return atl, ctl, last_long_run_pace, last_long_run_duration, last_tempo_run_duration


# Function to generate the weekly training plan
def generate_weekly_plan(week_num, last_week_long_run_duration, last_week_tempo_run_duration,
                         last_long_run_pace, last_tempo_run_pace, atl, ctl):
    long_run_duration = adjust_duration(week_num, last_week_long_run_duration)
    tempo_run_duration = adjust_duration(week_num, last_week_tempo_run_duration)

    long_run_duration = min(long_run_duration, MAX_LONG_RUN_DURATION)
    tempo_run_duration = min(tempo_run_duration, MAX_TEMPO_RUN_DURATION)

    avg_power_long_run = 180  # Example value for long run
    avg_power_tempo_run = 220  # Example value for tempo runs
    avg_hr_long_run = 140  # Example average heart rate for long run
    avg_hr_tempo_run = 160  # Example average heart rate for tempo run

    trimp_long_run = estimate_trimp(long_run_duration, avg_hr_long_run)
    trimp_tempo_run = estimate_trimp(tempo_run_duration, avg_hr_tempo_run)

    long_run_estimated_pace = estimate_pace(last_long_run_pace, atl, ctl, trimp_long_run, avg_hr_long_run,
                                            avg_power_long_run)
    tempo_run_estimated_pace = estimate_pace(last_tempo_run_pace, atl, ctl, trimp_tempo_run, avg_hr_tempo_run,
                                             avg_power_tempo_run)
    tempo_run_2_estimated_pace = long_run_estimated_pace

    long_run_distance = calculate_distance(long_run_duration, long_run_estimated_pace)
    tempo_run_1_distance = calculate_distance(tempo_run_duration, tempo_run_estimated_pace)
    tempo_run_2_distance = calculate_distance(tempo_run_duration, tempo_run_2_estimated_pace)

    return [
        {'type': 'long_run', 'duration': long_run_duration, 'avg_hr': avg_hr_long_run,
         'avg_power': avg_power_long_run, 'trimp': trimp_long_run, 'pace': long_run_estimated_pace,
         'distance': long_run_distance},
        {'type': 'tempo_run_1', 'duration': tempo_run_duration, 'avg_hr': avg_hr_tempo_run,
         'avg_power': avg_power_tempo_run, 'trimp': trimp_tempo_run, 'pace': tempo_run_estimated_pace,
         'distance': tempo_run_1_distance},
        {'type': 'tempo_run_2', 'duration': tempo_run_duration, 'avg_hr': avg_hr_tempo_run,
         'avg_power': avg_power_long_run, 'trimp': trimp_long_run, 'pace': tempo_run_2_estimated_pace,
         'distance': tempo_run_2_distance},
    ], long_run_duration, tempo_run_duration

def load_historical_runs_file(filename=None, csvData=None):
    if csvData:
        csv_file = StringIO(csvData)
    historical_runs = []

    def parse_duration(duration_str):
        time_parts = list(map(int, duration_str.split(':')))
        hours = time_parts[0]
        minutes = time_parts[1]
        seconds = time_parts[2]
        return hours * 60 + minutes + seconds / 60

    def parse_pace(pace_str):
        minutes, seconds = map(int, pace_str.split(':'))
        return minutes + seconds / 60

    with open(filename, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            historical_runs.append({
                'date': datetime.strptime(row['date'], '%Y-%m-%d'),
                'vo2max': float(row['vo2max']),
                'avg_power': float(row['avg_power']),
                'avg_hr': float(row['avg_hr']),
                'duration': parse_duration(row['duration']),
                'pace': parse_pace(row['pace']),
                'distance': float(row['distance']),
                'trimp': float(row['trimp']),
                'run_type': row['run_type']
            })

    return historical_runs

def load_historical_runs_memory(csvData):
    historical_runs = []

    def parse_duration(duration_str):
        time_parts = list(map(int, duration_str.split(':')))
        hours = time_parts[0]
        minutes = time_parts[1]
        seconds = time_parts[2]
        return hours * 60 + minutes + seconds / 60

    def parse_pace(pace_str):
        minutes, seconds = map(int, pace_str.split(':'))
        return minutes + seconds / 60

    csv_file = StringIO(csvData)
    reader = csv.DictReader(csv_file)
    for row in reader:
        historical_runs.append({
            'date': datetime.strptime(row['date'], '%Y-%m-%d'),
            'vo2max': float(row['vo2max']),
            'avg_power': float(row['avg_power']),
            'avg_hr': float(row['avg_hr']),
            'duration': parse_duration(row['duration']),
            'pace': parse_pace(row['pace']),
            'distance': float(row['distance']),
            'trimp': float(row['trimp']),
            'run_type': row['run_type']
        })

    return historical_runs


def load_historic_runs(config, historical_runs):
    #historical_runs = load_historical_runs_file('historical_runs.csv',historical_runs )
    historical_runs = load_historical_runs_memory(historical_runs)
    initial_atl, initial_ctl, last_run_pace, last_long_run_duration, last_tempo_run_duration = calculate_fitness_from_history(
        historical_runs)
    initial_long_run_pace = last_run_pace
    initial_tempo_run_pace = last_run_pace  # Assume same for simplicity
    config = {
        'initial_atl': float(initial_atl),
        'initial_ctl': float(initial_ctl),
        'num_weeks': config['num_weeks'],
        'long_run_duration': float(last_long_run_duration),
        'tempo_run_duration': float(last_tempo_run_duration),
        'long_run_pace': float(last_run_pace),
        'tempo_run_pace': float(last_run_pace),
        'start_date': config['start_date'],
        'end_date': config['end_date']
    }
    return config, historical_runs

def get_current_week(start_date):
    if isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Invalid date format for start_date: {start_date}. Expected 'YYYY-MM-DD'.")

    today_date_obj = datetime.today()

    if start_date > today_date_obj:
        raise ValueError("start_date cannot be in the future.")

    days_difference = (today_date_obj - start_date).days
    current_week = days_difference // 7

    return current_week + 1  # Weeks start at 1, not 0

def calculate_week_start_end_dates(start_date, week_num):
    """
    Calculate the start and end date of the week given a start date and a week number.
    The week starts on Monday and ends on Sunday.
    """
    # Check if start_date is a string and convert to datetime
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')

    week_start = start_date + timedelta(weeks=week_num - 1)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end

def add_historical_runs_to_plan(training_plan, start_date, current_week, historical_runs):
    """
    Add historical runs to the training plan for each week from week 1 to the current_week
    based on whether the run date falls within the week.
    """

    # Iterate from week 1 to the current week
    for week_num in range(1, current_week + 1):
        # Calculate the start and end dates for this week
        week_start, week_end = calculate_week_start_end_dates(start_date, week_num)

        week_data = {
            'week': week_num,
            'week_sunday': week_end.strftime('%Y-%m-%d'),  # The end of the week is Sunday
            'plan': []
        }

        # Filter historical runs that belong to this week based on the run date
        runs_for_this_week = [
            run for run in historical_runs
            if week_start <= run['date'] <= week_end
        ]

        # Add historical runs to the plan for this week
        for run in runs_for_this_week:
            # Format each run (e.g., duration, pace, etc.)
            formatted_run = {
                'type': run['run_type'],
                'duration': run['duration'],  # Assume duration is already formatted
                'avg_power': run['avg_power'],
                'avg_hr': run['avg_hr'],
                'trimp': round(run['trimp'], 2),
                'pace': run['pace'],  # Assume pace is already formatted
                'distance': run['distance']
            }
            week_data['plan'].append(formatted_run)

        # Append the weekly data to the training plan
        training_plan.append(week_data)

    return training_plan


# Function to simulate the training plan
def simulate_training_plan(config=None, historical_runs=None):
    if historical_runs:
        #config = general_config = load_config("config.json") #change this to get the start and end date
        config, historical_runs = load_historic_runs(config, historical_runs)

    config_filename = 'general_config.json'
    general_config = load_config(config_filename)
    keys_to_assign = ['PROGRESSIVE_OVERLOAD', 'MAX_LONG_RUN_DURATION', 'MAX_TEMPO_RUN_DURATION',
                      'MAX_HEART_RATE', 'RESTING_HEART_RATE']

    for key in keys_to_assign:
        globals()[key] = general_config.get(key)

    training_plan = []
    atl = config['initial_atl']
    ctl = config['initial_ctl']

    last_long_run_duration = config['long_run_duration']
    last_tempo_run_duration = config['tempo_run_duration']
    last_long_run_pace = config['long_run_pace']
    last_tempo_run_pace = config['tempo_run_pace']

    start_date = config['start_date']
    end_date = config['end_date']
    num_weeks = calculate_num_weeks(start_date, end_date)
    current_week = get_current_week(start_date)

    for week in range(current_week, num_weeks + 1):
        weekly_plan, long_run_duration, tempo_run_duration = generate_weekly_plan(
            week, last_long_run_duration, last_tempo_run_duration, last_long_run_pace, last_tempo_run_pace, atl, ctl)

        training_plan.append({
            'week': week,
            'plan': weekly_plan
        })

        # Update last run durations and paces for the next week
        last_long_run_duration = long_run_duration
        last_tempo_run_duration = tempo_run_duration
        last_long_run_pace = weekly_plan[0]['pace']
        last_tempo_run_pace = weekly_plan[1]['pace']

        # Simulate the training week
        atl, ctl, tsb, total_trimp = simulate_week(weekly_plan, atl, ctl)
        print(f"Week {week}: ATL={atl:.2f}, CTL={ctl:.2f}, TSB={tsb:.2f}, Total TRIMP={total_trimp:.2f}")

    #Add History
    start_date = config['start_date']
    current_week = get_current_week(start_date) - 1
    training_plan = add_historical_runs_to_plan(training_plan, start_date, current_week, historical_runs)
    training_plan = sorted(training_plan, key=lambda x: x['week'])

    return training_plan


# Function to format time as mm:ss or hh:mm
def format_time(minutes, is_pace=False):
    total_seconds = int(minutes * 60)
    mins = total_seconds // 60
    secs = total_seconds % 60

    if is_pace:
        # Calculate speed in km/h
        # speed = 60 / minutes
        # return f"{speed:.2f} km/h"  # Speed format in km/h
        return f"{mins}:{secs:02d} min/km"
    else:
        # Handle time formatting for both < 60 min and >= 60 min cases
        if minutes < 60:
            return f"{mins}:{secs:02d} min"  # mm:ss format for time
        else:
            hours = mins // 60
            mins = mins % 60
            return f"{hours}:{mins:02d} h"  # hh:mm format for long durations


# Function to calculate the date of the Sunday for a given week number
from datetime import datetime, timedelta


def calculate_sunday_date(start_date, week_num):
    # Check if start_date is a string and convert it to a datetime object if necessary
    if isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")  # Adjust format as needed
        except ValueError:
            raise ValueError(f"Invalid date format for start_date: {start_date}. Expected format: YYYY-MM-DD.")

    # Calculate the date for the specified week number
    return start_date + timedelta(weeks=week_num - 1)


def format_results(training_plan, start_date):
    """
    Format the results of the training plan:
    - Format distances to two decimal places
    - Format time and pace using format_time function
    - Add a 'week_sunday' value to each week, which represents the date of that week's Sunday
    """
    formatted_plan = []

    for week_data in training_plan:
        formatted_week = {
            'week': week_data['week'],
            'week_sunday': calculate_sunday_date(start_date, week_data['week']).strftime('%Y-%m-%d'),
            # Adding week_sunday
            'plan': []
        }

        for session in week_data['plan']:
            formatted_session = {
                'type': session['type'],
                'duration': format_time(session['duration'], False),  # Format duration using format_time
                'avg_hr': session['avg_hr'],
                'avg_power': session['avg_power'],
                'trimp': round(session['trimp'], 2),  # Round trimp to 2 decimal places
                'pace': format_time(session['pace'], True),  # Format pace using format_time
                'distance': f"{session['distance']:.2f} km"  # Format distance to 2 decimal places
            }
            formatted_week['plan'].append(formatted_session)

        formatted_plan.append(formatted_week)

    race_plan = []
    for session in training_plan[-1]['plan']:
        if session['type'] == 'long_run':
            long_run_pace = session['pace']
            long_run_distance = session['distance']
        elif session['type'] == 'tempo_run_1':
            tempo_run_pace = session['pace']
            tempo_run_distance = session['distance']

    #if enough km to tun half marathon
    if (tempo_run_distance + long_run_distance) >18 :
        long_race_distance = (21.1 * 2 / 3)
        tempo_race_distance = (21.1 * 1 / 3)
    else:
        long_race_distance = (10 * 2 / 3)
        tempo_race_distance = (10 * 1 / 3)


    long_race_time = long_race_distance * long_run_pace
    tempo_race_time = tempo_race_distance * tempo_run_pace

    slow_run = {
        "distance": f"{long_race_distance:.2f} km",
        "pace": format_time(long_run_pace, True),
        "time": format_time(long_race_time, False),
        "type": "Slow Run"
    }

    fast_run = {
        "distance": f"{tempo_race_distance:.2f} km",  # Fixed quote and corrected precision
        "pace": format_time(tempo_run_pace, True),
        "time": format_time(tempo_race_time, False),
        "type": "Fast Run"
    }

    race_plan.append(slow_run)
    race_plan.append(fast_run)
    total_time = {"total_time": format_time(long_race_time + tempo_race_time)}

    return formatted_plan, race_plan, total_time


# Load configuration data from a JSON file
def load_config(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Configuration file {filename} not found.")
        return {}


# Export the training plan to a CSV file
def export_to_csv(training_plan, filename='training_plan.csv'):
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Week', 'Type', 'Duration', 'Avg HR', 'Avg Power', 'TRIMP', 'Pace', 'Distance'])
        for week_num, week in enumerate(training_plan, start=1):
            for session in week:
                writer.writerow([week_num, session['type'], session['duration'], session['avg_hr'],
                                 session['avg_power'], session['trimp'], session['pace'], session['distance']])
    print(f"Training plan exported to {filename}.")


if __name__ == "__main__":
    config = {
        'initial_atl': 100,
        'initial_ctl': 200,
        'initial_long_run_duration': 60,
        'initial_tempo_run_duration': 30,
        'initial_long_run_pace': 6,
        'initial_tempo_run_pace': 5,
        'start_date': '2023-01-01',
        'end_date': '2024-01-01'
    }

    training_plan = simulate_training_plan(config)
    export_to_csv(training_plan)
