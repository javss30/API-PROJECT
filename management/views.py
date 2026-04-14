
import json
import re
from collections import defaultdict
from datetime import timedelta

from django import forms
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Sum, Count
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Athlete, Coach, PerformanceRecord, TrainingSession, Payment, Notification, Evaluation, Goal, Team, Announcement, Message, GameRecord, BasketballStat, Incident, Attendance
from .forms import AthleteForm, CoachForm, UserCreationByAdminForm, UserUpdateByCoachForm, TrainingSessionForm, PaymentForm, AthleteProfileForm, PerformanceRecordForm, EvaluationForm, GoalForm

@login_required
def monitor_progress(request):
    # Only Coaches and Admins can monitor progress
    is_coach = Coach.objects.filter(user=request.user).exists()
    if not request.user.is_superuser and not is_coach:
        return redirect('home')
    
    coach = None
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athletes = Athlete.objects.filter(sports__in=coach_sports)
    else:
        athletes = Athlete.objects.all()
        
    selected_athlete_id = request.GET.get('athlete_id')
    selected_athlete = None
    evaluations = []
    goals = []
    performance_records = []
    sessions_stats = {'Completed': 0, 'Missed': 0, 'Scheduled': 0}
    
    if selected_athlete_id:
        selected_athlete = get_object_or_404(Athlete, id=selected_athlete_id)
        evaluations = selected_athlete.evaluations.all().order_by('-date')
        goals = selected_athlete.goals.all()
        performance_records = PerformanceRecord.objects.filter(athlete=selected_athlete).order_by('-record_date')
        
        # Determine sport labels for analytics update
        athlete_sports = str(selected_athlete.sports or "").lower()
        if 'volleyball' in athlete_sports:
            m1_label, m2_label = 'Attack Success %', 'Service Accuracy'
        elif 'sepak takraw' in athlete_sports:
            m1_label, m2_label = 'Spike Success %', 'Serve Accuracy'
        else:
            m1_label, m2_label = 'Field Goal %', '3-Point Accuracy'

        # Get session stats
        sessions = TrainingSession.objects.filter(athlete=selected_athlete)
        for status in sessions_stats.keys():
            sessions_stats[status] = sessions.filter(status=status).count()
    elif athletes.exists():
        selected_athlete = athletes.first()

    # Determine sport labels for UI
    coach_sports_str = str(coach.sports or "").lower() if coach else ""
    sport_type = 'Basketball'
    if 'vol' in coach_sports_str:
        sport_type = 'Volleyball'
    elif 'sepak' in coach_sports_str:
        sport_type = 'Sepak Takraw'
    
    if sport_type == 'Volleyball':
        label1, label2, label3 = 'Aces', 'Kills', 'Blocks'
        sport_icon = 'volleyball'
    elif sport_type == 'Sepak Takraw':
        label1, label2, label3 = 'Spikes', 'Serves', 'Blocks'
        sport_icon = 'circle-dashed'
    else:
        # Fallback
        first_athlete = athletes.first()
        athlete_sport = str(first_athlete.sports or "").lower() if first_athlete else ""
        if 'vol' in athlete_sport:
            label1, label2, label3 = 'Aces', 'Kills', 'Blocks'
            sport_icon = 'volleyball'
        elif 'sepak' in athlete_sport:
            label1, label2, label3 = 'Spikes', 'Serves', 'Blocks'
            sport_icon = 'circle-dashed'
        else:
            label1, label2, label3 = 'PTS', 'AST', 'REB'
            sport_icon = 'activity'

    # Prepare athlete data for the frontend 'players' object
    athletes_data = {}
    for athlete in athletes:
        stat, _ = BasketballStat.objects.get_or_create(athlete=athlete)
        evals = athlete.evaluations.all().order_by('-date')
        athlete_goals = athlete.goals.all()
        athlete_games = athlete.game_records.all().order_by('-date', '-id')
        
        # Helper to extract numbers from strings like "25 pts"
        def get_val(v):
            if not v: return 0
            if isinstance(v, (int, float)): return int(v)
            nums = re.findall(r"\d+", str(v))
            return int(nums[0]) if nums else 0

        # Build games history list
        games_history = []
        wins = 0
        losses = 0
        for g in athlete_games:
            if g.win:
                wins += 1
            else:
                losses += 1
            games_history.append({
                'opponent': g.opponent,
                'subtitle': 'COMPETITIVE PLAY',
                'date': g.date.strftime('%B %d, %Y').upper(),
                'venue': g.venue,
                'pts': g.points,
                'ast': g.assists,
                'reb': g.rebounds,
                'win': g.win
            })
        
        # If no individual records, add the accumulated total as a fallback row
        if not games_history:
            games_history.append({
                'opponent': 'Season Total', 
                'subtitle': 'ACCUMULATED', 
                'date': '2026', 
                'venue': 'Various', 
                'pts': stat.points, 
                'ast': stat.assists, 
                'reb': stat.rebounds, 
                'win': True
            })
            wins = 1

        evaluations_list = []
        for e in evals:
            # Use full name if available, otherwise username
            coach_name = e.coach.get_full_name() or e.coach.username if e.coach else "Unknown"
            evaluations_list.append({
                'date': e.date.strftime('%B %d, %Y').upper(),
                'coach': coach_name.upper(),
                'text': e.notes
            })

        att_qs = Attendance.objects.filter(athlete=athlete)
        attendance_total = att_qs.count()
        attendance_missed = att_qs.filter(status='Absent').count()
        if attendance_total > 0:
            attendance_rate = round(((attendance_total - attendance_missed) / attendance_total) * 100, 1)
            sessions_done = attendance_total - attendance_missed
            sessions_miss = attendance_missed
        else:
            sessions_done = TrainingSession.objects.filter(athlete=athlete, status='Completed').count()
            sessions_miss = TrainingSession.objects.filter(athlete=athlete, status='Missed').count()
            attendance_rate = round((sessions_done / (sessions_done + sessions_miss) * 100), 1) if (sessions_done + sessions_miss) else 100.0

        athletes_data[str(athlete.id)] = {
            'name': athlete.user.get_full_name() or athlete.user.username,
            'profile_picture': athlete.profile_picture.url if athlete.profile_picture else None,
            'jersey_number': athlete.jersey_number or "#--",
            'wins': wins,
            'losses': losses,
            'physical': {
                'weight': f"{athlete.weight} kg" if hasattr(athlete, 'weight') else "0.00 kg",
                'endurance': 'HIGH' # Mocking endurance for now
            },
            'goals': {
                'current': sum(get_val(g.current_value) for g in athlete_goals) if athlete_goals else 0,
                'target': sum(get_val(g.target_value) for g in athlete_goals) if athlete_goals else 100
            },
            'attendance': attendance_rate,
            'sessions': {
                'done': sessions_done,
                'miss': sessions_miss,
                'sched': TrainingSession.objects.filter(athlete=athlete, status='Scheduled').count()
            },
            'evaluations': evaluations_list[:5],
            'games': games_history,
            'speed': float(stat.speed)
        }

    context = {
        'athletes': athletes,
        'athletes_data_json': json.dumps(athletes_data),
        'selected_athlete': selected_athlete,
        'm1_label': m1_label if selected_athlete_id else '',
        'm2_label': m2_label if selected_athlete_id else '',
        'stat_labels': {'l1': label1, 'l2': label2, 'l3': label3},
        'sport_icon': sport_icon,
        'evaluations': evaluations,
        'goals': goals,
        'performance_records': performance_records,
        'sessions_stats': sessions_stats,
        'in_portal': True,
        'portal_type': 'coach' if is_coach else 'admin'
    }
    return render(request, 'management/monitor_progress.html', context)

@login_required
def add_evaluation(request, athlete_id):
    if not request.user.is_superuser and not Coach.objects.filter(user=request.user).exists():
        return redirect('home')
        
    athlete = get_object_or_404(Athlete, id=athlete_id)
    if request.method == 'POST':
        data = request.POST.copy()
        if 'speed_trend' not in data: data['speed_trend'] = 'Stable'
        if 'strength_trend' not in data: data['strength_trend'] = 'Stable'
        if 'attendance_rate' not in data: data['attendance_rate'] = '100'
        
        form = EvaluationForm(data)
        if form.is_valid():
            evaluation = form.save(commit=False)
            evaluation.athlete = athlete
            evaluation.coach = request.user
            evaluation.save()
            messages.success(request, f"Evaluation added for {athlete.user.username}")
            return redirect(f'/athletes/monitor-progress/?athlete_id={athlete_id}')
    return redirect(f'/athletes/monitor-progress/?athlete_id={athlete_id}')

@login_required
def add_goal(request, athlete_id):
    if not request.user.is_superuser and not Coach.objects.filter(user=request.user).exists():
        return redirect('home')
        
    athlete = get_object_or_404(Athlete, id=athlete_id)
    if request.method == 'POST':
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.athlete = athlete
            goal.save()
            messages.success(request, f"Goal added for {athlete.user.username}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error in {field}: {error}")
    return redirect(f'/athletes/monitor-progress/?athlete_id={athlete_id}')

@login_required
def update_goal(request, goal_id):
    if not request.user.is_superuser and not Coach.objects.filter(user=request.user).exists():
        return redirect('home')
        
    goal = get_object_or_404(Goal, id=goal_id)
    if request.method == 'POST':
        goal.current_value = request.POST.get('current_value')
        goal.status = request.POST.get('status')
        goal.save()
        messages.success(request, f"Goal '{goal.title}' updated successfully.")
    return redirect(f'/athletes/monitor-progress/?athlete_id={goal.athlete.id}')

@login_required
def delete_goal(request, goal_id):
    if not request.user.is_superuser and not Coach.objects.filter(user=request.user).exists():
        return redirect('home')
        
    goal = get_object_or_404(Goal, id=goal_id)
    athlete_id = goal.athlete.id
    goal.delete()
    messages.success(request, "Goal deleted successfully.")
    return redirect(f'/athletes/monitor-progress/?athlete_id={athlete_id}')

@login_required
def add_performance_record(request, athlete_id):
    if not request.user.is_superuser and not Coach.objects.filter(user=request.user).exists():
        return redirect('home')
        
    athlete = get_object_or_404(Athlete, id=athlete_id)
    if request.method == 'POST':
        form = PerformanceRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.athlete = athlete
            record.save()
            messages.success(request, f"Performance record added for {athlete.user.username}")
    return redirect(f'/athletes/monitor-progress/?athlete_id={athlete_id}')

def get_performance_chart_data(performance_data):
    """Returns data formatted for ApexCharts"""
    if not performance_data.exists():
        return None
        
    # Get unique metrics and dates
    metrics = list(performance_data.values_list('metric', flat=True).distinct())
    # Sort dates
    dates = sorted(list(set(performance_data.values_list('record_date', flat=True))))
    
    series = []
    for metric in metrics:
        metric_data = []
        for d in dates:
            record = performance_data.filter(metric=metric, record_date=d).first()
            if record:
                try:
                    # Extract numeric value
                    val_str = str(record.value)
                    # Simple numeric extraction
                    nums = re.findall(r"[-+]?\d*\.\d+|\d+", val_str)
                    val = float(nums[0]) if nums else 0
                    metric_data.append(val)
                except (ValueError, IndexError):
                    metric_data.append(0)
            else:
                metric_data.append(None) # Use None for missing data points
        
        series.append({
            'name': metric,
            'data': metric_data
        })
        
    return {
        'series': series,
        'categories': [d.strftime('%Y-%m-%d') for d in dates]
    }


def _normalize_metric_key(metric_name):
    return re.sub(r"[^a-z0-9]+", " ", str(metric_name or "").lower()).strip()


def _extract_numeric_metric_value(value):
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(value or ""))
    return float(nums[0]) if nums else None


def _dashboard_metric_specs(current_sport, performance_data):
    if current_sport == 'Basketball':
        return [
            {
                'key': 'attendance consistency',
                'label': 'Attendance Consistency',
                'aliases': {'attendance consistency'},
                'kind': 'percentage',
                'unit': '%',
                'baseline': (0.0, 100.0),
            },
            {
                'key': 'field goal',
                'label': 'Field Goal %',
                'aliases': {'field goal', 'field goal %'},
                'kind': 'percentage',
                'unit': '%',
                'baseline': (0.0, 100.0),
            },
            {
                'key': 'assists',
                'label': 'Assists',
                'aliases': {'assists', 'assist'},
                'kind': 'count_higher_better',
                'unit': '',
                'baseline': (0.0, 15.0),
            },
            {
                'key': 'rebounds',
                'label': 'Rebounds',
                'aliases': {'rebounds', 'rebound'},
                'kind': 'count_higher_better',
                'unit': '',
                'baseline': (0.0, 20.0),
            },
        ]

    labels = []
    for metric_name in performance_data.values_list('metric', flat=True).distinct():
        if not metric_name:
            continue
        labels.append({
            'key': _normalize_metric_key(metric_name),
            'label': metric_name,
            'aliases': {_normalize_metric_key(metric_name)},
            'kind': 'percentage',
            'unit': '',
            'baseline': (0.0, 100.0),
        })
    return labels[:5]


def _score_metric_value(metric_spec, value, metric_range):
    if value is None:
        return None

    kind = metric_spec['kind']
    if kind == 'percentage':
        return round(max(0.0, min(value, 100.0)), 1)

    lower, upper = metric_range
    if upper <= lower:
        lower, upper = metric_spec['baseline']
    if upper <= lower:
        return 100.0

    if kind == 'time_lower_better':
        score = ((upper - value) / (upper - lower)) * 100.0
    else:
        score = ((value - lower) / (upper - lower)) * 100.0
    return round(max(0.0, min(score, 100.0)), 1)

def _build_basketball_chart_records(athletes, metric_specs):
    if not athletes.exists():
        return []

    athlete_ids = list(athletes.values_list('id', flat=True))
    records = []

    attendance_daily = (
        Attendance.objects.filter(athlete_id__in=athlete_ids)
        .values('date')
        .annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='Present'))
        )
        .order_by('date')
    )
    for row in attendance_daily:
        total = row['total'] or 0
        if total:
            records.append({
                'date': row['date'],
                'metric_key': 'attendance consistency',
                'value': round((row['present'] / total) * 100, 1),
            })

    field_goal_records = PerformanceRecord.objects.filter(
        athlete_id__in=athlete_ids,
        metric__in=['Field Goal %', 'Field Goal']
    ).values('record_date', 'value')
    for row in field_goal_records:
        numeric_value = _extract_numeric_metric_value(row['value'])
        if numeric_value is not None:
            records.append({
                'date': row['record_date'],
                'metric_key': 'field goal',
                'value': numeric_value,
            })

    game_daily = (
        GameRecord.objects.filter(athlete_id__in=athlete_ids)
        .values('date')
        .annotate(
            assists=Sum('assists'),
            rebounds=Sum('rebounds'),
            games=Count('id'),
        )
        .order_by('date')
    )
    for row in game_daily:
        games_count = row['games'] or 0
        if row['assists'] is not None and games_count:
            records.append({
                'date': row['date'],
                'metric_key': 'assists',
                'value': round(float(row['assists']) / games_count, 1),
            })
        if row['rebounds'] is not None and games_count:
            records.append({
                'date': row['date'],
                'metric_key': 'rebounds',
                'value': round(float(row['rebounds']) / games_count, 1),
            })

    return records


def build_interactive_performance_chart_data(performance_data, current_sport, athletes=None):
    metric_specs = _dashboard_metric_specs(current_sport, performance_data)
    alias_map = {}
    for spec in metric_specs:
        for alias in spec['aliases']:
            alias_map[alias] = spec['key']

    parsed_records = []
    metric_ranges = {
        spec['key']: [spec['baseline'][0], spec['baseline'][1]]
        for spec in metric_specs
    }

    if current_sport == 'Basketball' and athletes is not None:
        parsed_records = _build_basketball_chart_records(athletes, metric_specs)
    else:
        if not performance_data.exists():
            return None

        for row in performance_data.values('record_date', 'metric', 'value'):
            normalized = _normalize_metric_key(row['metric'])
            metric_key = alias_map.get(normalized)
            if not metric_key:
                continue

            numeric_value = _extract_numeric_metric_value(row['value'])
            if numeric_value is None:
                continue

            parsed_records.append({
                'date': row['record_date'],
                'metric_key': metric_key,
                'value': numeric_value,
            })

    for item in parsed_records:
        spec = next((candidate for candidate in metric_specs if candidate['key'] == item['metric_key']), None)
        if not spec:
            continue
        if spec['kind'] in {'time_lower_better', 'count_higher_better'}:
            metric_ranges[item['metric_key']][0] = min(metric_ranges[item['metric_key']][0], item['value'])
            metric_ranges[item['metric_key']][1] = max(metric_ranges[item['metric_key']][1], item['value'])

    if not parsed_records:
        return None

    latest_date = max(item['date'] for item in parsed_records)
    records_by_metric = defaultdict(list)
    for item in parsed_records:
        records_by_metric[item['metric_key']].append(item)
    for metric_key in records_by_metric:
        records_by_metric[metric_key].sort(key=lambda row: row['date'])

    def build_period(days):
        start_date = latest_date - timedelta(days=days - 1)
        categories = [
            (start_date + timedelta(days=offset)).strftime('%Y-%m-%d')
            for offset in range(days)
        ]
        grouped_values = defaultdict(lambda: defaultdict(list))

        for item in parsed_records:
            if start_date <= item['date'] <= latest_date:
                grouped_values[item['metric_key']][item['date'].strftime('%Y-%m-%d')].append(item['value'])

        series = []
        for spec in metric_specs:
            points = []
            has_values = False
            metric_history = records_by_metric.get(spec['key'], [])
            last_known_value = None
            for historic_row in metric_history:
                if historic_row['date'] < start_date:
                    last_known_value = historic_row['value']
                else:
                    break
            for category in categories:
                values = grouped_values[spec['key']].get(category, [])
                if values:
                    raw_average = round(sum(values) / len(values), 1)
                    score = _score_metric_value(spec, raw_average, tuple(metric_ranges[spec['key']]))
                    suffix = spec['unit'] or ''
                    points.append({
                        'x': category,
                        'y': score,
                        'raw': f"{raw_average:.1f}{suffix}",
                    })
                    has_values = True
                    last_known_value = raw_average
                else:
                    if last_known_value is not None:
                        score = _score_metric_value(spec, last_known_value, tuple(metric_ranges[spec['key']]))
                        suffix = spec['unit'] or ''
                        points.append({
                            'x': category,
                            'y': score,
                            'raw': f"{last_known_value:.1f}{suffix} (carry)",
                        })
                        has_values = True
                    else:
                        points.append({
                            'x': category,
                            'y': None,
                            'raw': None,
                        })

            if has_values:
                series.append({
                    'name': spec['label'],
                    'data': points,
                })

        return {
            'categories': categories,
            'series': series,
            'start': start_date.strftime('%Y-%m-%d'),
            'end': latest_date.strftime('%Y-%m-%d'),
        }

    weekly = build_period(7)
    monthly = build_period(30)

    if not weekly['series'] and not monthly['series']:
        return None

    default_period = 'weekly' if weekly['series'] else 'monthly'
    return {
        'defaultPeriod': default_period,
        'periods': {
            'weekly': weekly,
            'monthly': monthly,
        },
        'yAxisTitle': 'Performance Score',
    }

def render_coach_dashboard(request, coach):
    # Filter athletes by coach's sport
    coach_sports = coach.sports.split(',') if coach.sports else []
    
    athletes = Athlete.objects.filter(sports__in=coach_sports) if coach_sports else Athlete.objects.none()
    athletes_count = athletes.count()
    
    sessions = TrainingSession.objects.filter(sports__in=coach_sports).order_by('-session_date')[:5] if coach_sports else TrainingSession.objects.none()
    sessions_count = TrainingSession.objects.filter(sports__in=coach_sports).count() if coach_sports else 0
    
    performance_data = PerformanceRecord.objects.filter(athlete__in=athletes)
    
    # Static chart for fallback/admin
    static_chart = generate_performance_chart(performance_data, f"{coach.sports} Performance Overview")
    # Interactive chart data
    interactive_chart_data = get_performance_chart_data(performance_data)

    # Recent Activity: Combination of athlete performance logs and evaluations
    # For a coach, show what athletes are doing
    recent_athlete_logs = PerformanceRecord.objects.filter(athlete__in=athletes).order_by('-record_date')[:5]
    recent_evaluations = Evaluation.objects.filter(athlete__in=athletes).order_by('-date')[:5]
    
    activity_feed = []
    for log in recent_athlete_logs:
        activity_feed.append({
            'type': 'performance',
            'athlete': log.athlete.user.username,
            'detail': f"logged {log.metric}: {log.value}",
            'date': log.record_date,
            'icon': 'fa-chart-line',
            'color': 'text-primary'
        })
    for eval in recent_evaluations:
        activity_feed.append({
            'type': 'evaluation',
            'athlete': eval.athlete.user.username,
            'detail': f"Evaluation: Speed {eval.speed_trend}, Strength {eval.strength_trend}",
            'date': eval.date,
            'icon': 'fa-clipboard-check',
            'color': 'text-success'
        })
    
    # Sort by date
    activity_feed.sort(key=lambda x: x['date'], reverse=True)
    activity_feed = activity_feed[:8]

    context = {
        'coach': coach,
        'athletes': athletes,
        'athletes_count': athletes_count,
        'sessions': sessions,
        'sessions_count': sessions_count,
        'chart': static_chart,
        'chart_data_json': json.dumps(interactive_chart_data) if interactive_chart_data else None,
        'activity_feed': activity_feed,
        'is_athlete': False,
        'portal_type': 'coach',
        'in_portal': True,
        'is_coach_dashboard': True,
        'coach_sport': coach.sports # For template differentiation
    }
    return render(request, 'management/coach_dashboard.html', context)

import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import json
import re
from django.http import HttpResponse
import csv
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout, authenticate

def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('management:dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

def home(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('management:dashboard')
        elif Coach.objects.filter(user=request.user).exists():
            return redirect('management:dashboard')
        elif Athlete.objects.filter(user=request.user).exists():
            return redirect('management:athlete_dashboard')
    featured_athletes = []
    for athlete in (
        Athlete.objects.select_related('user')
        .order_by('user__first_name', 'user__last_name', 'user__username')[:6]
    ):
        stats = BasketballStat.objects.filter(athlete=athlete).first()
        featured_athletes.append({
            'name': athlete.user.get_full_name().strip() or athlete.user.username,
            'role': athlete.position or 'Player',
            'jersey': athlete.jersey_number or '#--',
            'profile_picture': athlete.profile_picture.url if athlete.profile_picture else None,
            'username': athlete.user.username,
            'stat_line': (
                f"{stats.points} points | {stats.assists} assists | {stats.rebounds} rebounds"
                if stats else
                f"{athlete.sports or 'Athlete'} profile"
            ),
        })
    return render(request, 'management/gateway.html', {
        'in_portal': False,
        'featured_athletes': featured_athletes,
    })


def about_page(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('management:dashboard')
        elif Coach.objects.filter(user=request.user).exists():
            return redirect('management:dashboard')
        elif Athlete.objects.filter(user=request.user).exists():
            return redirect('management:athlete_dashboard')
    return render(request, 'management/about_page.html', {
        'in_portal': False
    })


def players_page(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('management:dashboard')
        elif Coach.objects.filter(user=request.user).exists():
            return redirect('management:dashboard')
        elif Athlete.objects.filter(user=request.user).exists():
            return redirect('management:athlete_dashboard')
    athletes = list(
        Athlete.objects.select_related('user')
        .order_by('user__first_name', 'user__last_name', 'user__username')
    )

    players = []
    for athlete in athletes:
        stats = BasketballStat.objects.filter(athlete=athlete).first()
        full_name = athlete.user.get_full_name().strip() or athlete.user.username
        if stats:
            stat_line = f"{stats.points} points | {stats.assists} assists | {stats.rebounds} rebounds"
        else:
            stat_line = f"{athlete.sports or 'Athlete'} profile"

        players.append({
            'name': full_name,
            'role': athlete.position or 'Player',
            'jersey': athlete.jersey_number or '#--',
            'profile_picture': athlete.profile_picture.url if athlete.profile_picture else None,
            'stat_line': stat_line,
            'username': athlete.user.username,
        })

    return render(request, 'management/players_page.html', {
        'in_portal': False,
        'players': players,
    })


def matches_page(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('management:dashboard')
        elif Coach.objects.filter(user=request.user).exists():
            return redirect('management:dashboard')
        elif Athlete.objects.filter(user=request.user).exists():
            return redirect('management:athlete_dashboard')

    matches = [
        {
            'date': 'Sept 30',
            'opponent': 'UC',
            'venue': 'Titan Arena',
            'time': '19:00',
            'status': 'Next Match',
            'status_tone': 'next',
            'is_featured': True,
        },
        {
            'date': 'Oct 7',
            'opponent': 'Thunder',
            'venue': 'Volt Stadium',
            'time': '18:30',
            'status': '',
            'status_tone': '',
            'is_featured': False,
        },
        {
            'date': 'Oct 14',
            'opponent': 'Sharks',
            'venue': 'Titan Arena',
            'time': '19:00',
            'status': '',
            'status_tone': '',
            'is_featured': False,
        },
        {
            'date': 'Oct 21',
            'opponent': 'Phoenix',
            'venue': 'Fire Court',
            'time': '20:00',
            'status': '',
            'status_tone': '',
            'is_featured': False,
        },
        {
            'date': 'Sept 23',
            'opponent': 'Titans',
            'venue': 'Titan Arena',
            'time': '19:00',
            'status': 'W 3-1',
            'status_tone': 'win',
            'is_featured': False,
        },
        {
            'date': 'Sept 16',
            'opponent': 'Eagles',
            'venue': 'Sky Arena',
            'time': '18:00',
            'status': 'W 3-0',
            'status_tone': 'win',
            'is_featured': False,
        },
    ]

    return render(request, 'management/matches_page.html', {
        'in_portal': False,
        'matches': matches,
    })


def unified_login(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('management:dashboard')
        if Coach.objects.filter(user=request.user).exists():
            return redirect('management:dashboard')
        if Athlete.objects.filter(user=request.user).exists():
            return redirect('athlete_portal_dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                if user.is_superuser or Coach.objects.filter(user=user).exists():
                    return redirect('management:dashboard')
                if Athlete.objects.filter(user=user).exists():
                    return redirect('athlete_portal_dashboard')
                logout(request)
                form.add_error(None, "This account does not have an assigned portal.")
            else:
                form.add_error(None, "Invalid credentials.")
    else:
        form = AuthenticationForm()

    return render(request, 'management/cyber_glass_login.html', {
        'form': form,
        'in_portal': True,
        'portal_type': 'unified',
        'login_variant': 'coach',
        'support_copy': 'Unified secure access for administrators, coaches, and athletes across the CEC ecosystem.'
    })

def coach_portal_landing(request):
    return render(request, 'management/coach_portal_landing.html', {
        'in_portal': True,
        'portal_type': 'coach'
    })

def admin_portal_landing(request):
    return render(request, 'management/admin_portal_landing.html', {
        'in_portal': True,
        'portal_type': 'admin'
    })

def coach_login(request):
    if request.user.is_authenticated:
        return redirect('management:dashboard')
    
    selected_sport = request.GET.get('sport')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                # Coaches Only
                if user.is_superuser:
                    form.add_error(None, "Admin credentials cannot be used here. Use the Admin Portal.")
                elif Coach.objects.filter(user=user).exists():
                    coach = Coach.objects.get(user=user)
                    coach_sports = coach.sports.split(',') if coach.sports else []
                    
                    # Verify sport portal if specified
                    if selected_sport and selected_sport not in coach_sports:
                        form.add_error(None, f"This account is not authorized to access the {selected_sport} portal. You are registered for {coach.sports}.")
                    else:
                        login(request, user)
                        return redirect('management:dashboard')
                else:
                    form.add_error(None, "This account is not registered as a Coach.")
            else:
                form.add_error(None, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'management/cyber_glass_login.html', {
        'form': form,
        'in_portal': True,
        'portal_type': 'coach',
        'selected_sport': selected_sport,
        'login_variant': 'coach',
        'support_copy': 'Authorized coaching access for practice strategy, roster control, and athlete oversight.'
    })

def admin_login(request):
    if request.user.is_authenticated:
        return redirect('management:dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None and user.is_superuser:
                login(request, user)
                return redirect('management:dashboard')
            elif user is not None:
                form.add_error(None, "Only administrators can access this portal.")
            else:
                form.add_error(None, "Invalid admin credentials.")
    else:
        form = AuthenticationForm()
    return render(request, 'management/cyber_glass_login.html', {
        'form': form,
        'in_portal': True,
        'portal_type': 'admin',
        'login_variant': 'admin',
        'support_copy': 'Restricted system access for management controls, records, and ecosystem settings.'
    })

from django.contrib import messages

@login_required
def evaluation_create(request):
    if request.method == 'POST':
        athlete_id = request.POST.get('athlete')
        notes = request.POST.get('notes')
        athlete = get_object_or_404(Athlete, id=athlete_id)
        Evaluation.objects.create(
            athlete=athlete,
            coach=request.user,
            notes=notes
        )
        messages.success(request, f"Feedback saved for {athlete.user.username}")
    return redirect(request.META.get('HTTP_REFERER', 'management:dashboard'))

@login_required
def announcement_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        sport = request.POST.get('sport')
        coach = Coach.objects.filter(user=request.user).first()
        if coach:
            Announcement.objects.create(
                coach=coach,
                sport=sport if sport else 'General',
                title=title,
                content=content
            )
            messages.success(request, "Announcement published successfully.")
    return redirect(request.META.get('HTTP_REFERER', 'management:dashboard'))

@login_required
def update_performance_analytics(request, athlete_id):
    if request.method == 'POST':
        athlete = get_object_or_404(Athlete, id=athlete_id)
        coach = Coach.objects.filter(user=request.user).first()
        if not coach and not request.user.is_superuser:
            return redirect('home')

        # Update jersey number if provided
        jersey_no = request.POST.get('jersey_number')
        if jersey_no:
            athlete.jersey_number = jersey_no
            athlete.save()

        # Determine sport to get correct labels
        current_sport = 'Basketball'
        if coach:
            sports_val = str(coach.sports or "").lower()
            if 'volleyball' in sports_val: current_sport = 'Volleyball'
            elif 'sepak takraw' in sports_val: current_sport = 'Sepak Takraw'

        if current_sport == 'Basketball':
            m1_label, m2_label = 'Field Goal %', '3-Point Accuracy'
        elif current_sport == 'Volleyball':
            m1_label, m2_label = 'Attack Success %', 'Service Accuracy'
        else:
            m1_label, m2_label = 'Spike Success %', 'Serve Accuracy'

        # Helper to calculate and save
        def save_metric(label, made, attempted):
            try:
                made = float(made)
                attempted = float(attempted)
                if attempted > 0:
                    percentage = round((made / attempted) * 100)
                    # Use filter and first to avoid MultipleObjectsReturned if duplicates exist
                    record = PerformanceRecord.objects.filter(athlete=athlete, metric=label).first()
                    if record:
                        record.value = str(percentage)
                        record.record_date = timezone.now().date()
                        record.save()
                    else:
                        PerformanceRecord.objects.create(
                            athlete=athlete,
                            metric=label,
                            value=str(percentage),
                            record_date=timezone.now().date()
                        )
            except (ValueError, TypeError):
                pass

        save_metric(m1_label, request.POST.get('m1_made'), request.POST.get('m1_attempted'))
        save_metric(m2_label, request.POST.get('m2_made'), request.POST.get('m2_attempted'))
        
        # Attendance Consistency
        try:
            attended = float(request.POST.get('attended'))
            total = float(request.POST.get('total_sessions'))
            if total > 0:
                attendance_pct = round((attended / total) * 100)
                record = PerformanceRecord.objects.filter(athlete=athlete, metric='Attendance Consistency').first()
                if record:
                    record.value = str(attendance_pct)
                    record.record_date = timezone.now().date()
                    record.save()
                else:
                    PerformanceRecord.objects.create(
                        athlete=athlete,
                        metric='Attendance Consistency',
                        value=str(attendance_pct),
                        record_date=timezone.now().date()
                    )
        except (ValueError, TypeError):
            pass

        messages.success(request, f"Analytics updated for {athlete.user.username}")
    
    return redirect(request.META.get('HTTP_REFERER', 'management:dashboard'))

from django.template.loader import render_to_string
from django.http import HttpResponse

@login_required
def generate_report_pdf(request):
    # This is a simplified version using HTML response. 
    # For a real PDF, you'd use a library like ReportLab or WeasyPrint.
    # We will provide a printable HTML view instead for simplicity in this demo.
    coach = Coach.objects.filter(user=request.user).first()
    athletes = Athlete.objects.filter(sports__icontains=coach.sports)
    
    context = {
        'coach': coach,
        'athletes': athletes,
        'today': timezone.now()
    }
    return render(request, 'management/report_print.html', context)

@login_required
def admin_register_coach(request):
    if not request.user.is_superuser:
        return redirect('home')
    
    if request.method == 'POST':
        user_form = UserCreationByAdminForm(request.POST)
        coach_form = CoachForm(request.POST, request.FILES)
        
        if user_form.is_valid() and coach_form.is_valid():
            password = user_form.cleaned_data.get('password')
            if not password:
                user_form.add_error('password', 'Password is required for new registration.')
            else:
                user = user_form.save(commit=False)
                user.set_password(password)
                user.save()
                
                coach = coach_form.save(commit=False)
                coach.user = user
                coach.plain_password = password
                coach.save()
                # Handle profile picture upload during registration
                if 'profile_picture' in request.FILES:
                    coach.profile_picture = request.FILES['profile_picture']
                    coach.save()
                messages.success(request, f"Coach account for '{user.username}' was created successfully!")
                return redirect('management:coach_list')
    else:
        user_form = UserCreationByAdminForm()
        coach_form = CoachForm()
        
    return render(request, 'management/admin_register_coach.html', {
        'user_form': user_form,
        'coach_form': coach_form,
        'in_portal': False
    })

@login_required
def admin_register_athlete(request):
    if not request.user.is_superuser:
        return redirect('home')
        
    if request.method == 'POST':
        user_form = UserCreationByAdminForm(request.POST)
        athlete_form = AthleteForm(request.POST, request.FILES)
        
        if user_form.is_valid() and athlete_form.is_valid():
            password = user_form.cleaned_data.get('password')
            if not password:
                user_form.add_error('password', 'Password is required for new registration.')
            else:
                user = user_form.save(commit=False)
                user.set_password(password)
                user.save()
                
                athlete = athlete_form.save(commit=False)
                athlete.user = user
                athlete.plain_password = password
                athlete.save()
                # Handle profile picture upload during registration
                if 'profile_picture' in request.FILES:
                    athlete.profile_picture = request.FILES['profile_picture']
                    athlete.save()
                messages.success(request, f"Athlete account for '{user.username}' was created successfully!")
                return redirect('management:athlete_list')
    else:
        user_form = UserCreationByAdminForm()
        athlete_form = AthleteForm()

    return render(request, 'management/admin_register_athlete.html', {
        'user_form': user_form,
        'athlete_form': athlete_form,
        'in_portal': False
    })

@login_required
def coach_list(request):
    if not request.user.is_superuser:
        return redirect('home')
    
    query = request.GET.get('query', '')
    coaches = Coach.objects.all()

    if query:
        coaches = coaches.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(contact_number__icontains=query) |
            Q(specialization__icontains=query) |
            Q(sports__icontains=query)
        )

    return render(request, 'management/coach_list.html', {'coaches': coaches})

@login_required
def coach_detail(request, pk):
    # Allow superusers, coaches, and athletes to view coach details
    is_coach = Coach.objects.filter(user=request.user).exists()
    is_athlete = Athlete.objects.filter(user=request.user).exists()
    
    if not request.user.is_superuser and not is_coach and not is_athlete:
        return redirect('home')
        
    coach = get_object_or_404(Coach, pk=pk)
    return render(request, 'management/coach_detail.html', {
        'coach': coach,
        'is_athlete': is_athlete,
        'in_portal': True,
        'portal_type': 'athlete' if is_athlete else ('coach' if is_coach else 'admin')
    })

@login_required
def coach_delete(request, pk):
    if not request.user.is_superuser:
        return redirect('home')
    coach = get_object_or_404(Coach, pk=pk)
    if request.method == 'POST':
        user = coach.user
        coach.delete()
        user.delete()
        messages.success(request, f"Coach {user.username} account has been deleted.")
        return redirect('management:coach_list')
    return render(request, 'management/coach_confirm_delete.html', {'coach': coach})

@login_required
def coach_update(request, pk):
    if not request.user.is_superuser:
        return redirect('home')
    coach = get_object_or_404(Coach, pk=pk)
    user = coach.user
    if request.method == 'POST':
        user_form = UserCreationByAdminForm(request.POST, instance=user)
        coach_form = CoachForm(request.POST, request.FILES, instance=coach)
        if user_form.is_valid() and coach_form.is_valid():
            # Save user without committing to avoid saving raw password if blank
            user = user_form.save(commit=False)
            
            # If password is provided, update it
            password = user_form.cleaned_data.get('password')
            if password:
                user.set_password(password)
                coach.plain_password = password
            
            user.save()
            coach_form.save()
            messages.success(request, f"Coach {user.username} information updated successfully.")
            return redirect('management:coach_detail', pk=pk)
    else:
        # Pre-fill the password field with plain_password if it exists
        user_form = UserCreationByAdminForm(instance=user, initial={'password': coach.plain_password})
        coach_form = CoachForm(instance=coach)
    return render(request, 'management/admin_register_coach.html', {
        'user_form': user_form,
        'coach_form': coach_form,
        'is_edit': True,
        'coach': coach
    })

def coach_landing(request):
    return render(request, 'management/landing.html', {
        'in_portal': False
    })

def athlete_portal_landing(request):
    athlete = None
    if request.user.is_authenticated:
        athlete = Athlete.objects.filter(user=request.user).first()
    return render(request, 'management/athlete_portal_landing.html', {
        'is_athlete': athlete is not None,
        'in_portal': True,
        'portal_type': 'athlete'
    })

def athlete_login(request):
    if request.user.is_authenticated:
        return redirect('athlete_portal_dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                # REJECT ADMINS AND COACHES - Athletes Only
                if user.is_superuser:
                    form.add_error(None, "Admin credentials cannot be used here. Use the Admin Portal.")
                elif Coach.objects.filter(user=user).exists():
                    form.add_error(None, "Coach credentials cannot be used here. Use the Coach Portal.")
                elif not Athlete.objects.filter(user=user).exists():
                    form.add_error(None, "This account is not registered as an athlete.")
                else:
                    login(request, user)
                    return redirect('athlete_portal_dashboard')
            else:
                form.add_error(None, "Invalid credentials.")
    else:
        form = AuthenticationForm()
    return render(request, 'management/cyber_glass_login.html', {
        'form': form,
        'in_portal': True,
        'portal_type': 'athlete',
        'login_variant': 'athlete',
        'support_copy': 'Secure athlete access for performance, schedule, payments, and progress tracking.'
    })

@login_required
def payment_list(request):
    is_coach = Coach.objects.filter(user=request.user).exists()
    is_athlete = Athlete.objects.filter(user=request.user).exists()
    
    Notification.objects.filter(recipient=request.user, notification_type='payment', is_read=False).update(is_read=True)
    
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        payments = Payment.objects.filter(sports__in=coach_sports)
    elif is_athlete:
        athlete = Athlete.objects.get(user=request.user)
        payments = Payment.objects.filter(athlete=athlete)
    else:
        payments = Payment.objects.all()
    
    return render(request, 'management/payment_list.html', {
        'payments': payments,
        'is_athlete': is_athlete,
        'portal_type': 'athlete' if is_athlete else ('coach' if is_coach else 'admin'),
        'in_portal': True
    })

@login_required
def payment_create(request):
    is_coach = Coach.objects.filter(user=request.user).exists()
    is_athlete = Athlete.objects.filter(user=request.user).exists()
    
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athletes = Athlete.objects.filter(sports__in=coach_sports)
    elif is_athlete:
        athlete = Athlete.objects.get(user=request.user)
        athletes = Athlete.objects.filter(id=athlete.id)
    else:
        athletes = Athlete.objects.all()

    athlete_sports_map = {str(a.id): a.sports for a in athletes}
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        form.fields['athlete'].queryset = athletes
            
        if form.is_valid():
            payment = form.save(commit=False)
            if is_coach:
                payment.sports = coach.sports
            elif is_athlete:
                athlete = athletes.first()
                payment.athlete = athlete
                payment.sports = athlete.sports
            payment.save()
            
            # Create a notification for Admin
            if not request.user.is_superuser:
                user_name = request.user.get_full_name() or request.user.username
                athlete_name = payment.athlete.user.get_full_name() or payment.athlete.user.username
                amount = f"{payment.amount:.2f}"
                
                role = "Athlete" if is_athlete else "Coach"
                Notification.objects.create(
                    title=f"New Payment recorded by {role}",
                    message=f"{role} {user_name} recorded a payment for {athlete_name} amounting to ${amount}.",
                    notification_type='payment'
                )
                
            return redirect('management:payment_list')
    else:
        form = PaymentForm()
        form.fields['athlete'].queryset = athletes
        if is_coach or is_athlete:
            if 'sports_selection' in form.fields:
                del form.fields['sports_selection']
        if is_athlete:
            # Pre-select the athlete and disable the field
            athlete = athletes.first()
            form.fields['athlete'].initial = athlete
            form.fields['athlete'].widget = forms.HiddenInput()
            
    return render(request, 'management/payment_form.html', {
        'form': form,
        'athlete_sports_map': athlete_sports_map,
        'is_athlete': is_athlete,
        'portal_type': 'athlete' if is_athlete else ('coach' if is_coach else 'admin'),
        'in_portal': True
    })

@login_required
def payment_update(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    is_coach = Coach.objects.filter(user=request.user).exists()
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athletes = Athlete.objects.filter(sports__in=coach_sports)
    else:
        athletes = Athlete.objects.all()

    athlete_sports_map = {str(a.id): a.sports for a in athletes}
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        form.fields['athlete'].queryset = athletes
        if form.is_valid():
            payment = form.save(commit=False)
            if is_coach:
                payment.sports = coach.sports
            payment.save()
            return redirect('management:payment_list')
    else:
        form = PaymentForm(instance=payment)
        form.fields['athlete'].queryset = athletes
        if is_coach:
            del form.fields['sports_selection']

    return render(request, 'management/payment_form.html', {
        'form': form,
        'athlete_sports_map': athlete_sports_map
    })

@login_required
def payment_delete(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        payment.delete()
        return redirect('management:payment_list')
    return render(request, 'management/payment_confirm_delete.html', {'payment': payment})

@login_required
def training_session_list(request):
    is_coach = Coach.objects.filter(user=request.user).exists()
    is_athlete = Athlete.objects.filter(user=request.user).exists()
    
    Notification.objects.filter(recipient=request.user, notification_type='session', is_read=False).update(is_read=True)
    
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        sessions = TrainingSession.objects.filter(sports__in=coach_sports)
    elif is_athlete:
        athlete = Athlete.objects.get(user=request.user)
        sessions = TrainingSession.objects.filter(athlete=athlete)
        # Add fallback coach for display if missing
        for s in sessions:
            if not s.coach:
                # Try to find a coach for the sport, preferring 'edwin macasero'
                default_coach = Coach.objects.filter(sports__icontains=s.sports, user__username__icontains='edwin').first()
                if not default_coach:
                    default_coach = Coach.objects.filter(sports__icontains=s.sports).first()
                if default_coach:
                    s.coach = default_coach
    else:
        sessions = TrainingSession.objects.all()
        
    return render(request, 'management/training_session_list.html', {
        'sessions': sessions,
        'is_athlete': is_athlete,
        'portal_type': 'athlete' if is_athlete else ('coach' if is_coach else 'admin'),
        'in_portal': True
    })

@login_required
def training_session_create(request):
    is_coach = Coach.objects.filter(user=request.user).exists()
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athletes = Athlete.objects.filter(sports__in=coach_sports)
    else:
        athletes = Athlete.objects.all()

    athlete_sports_map = {str(a.id): a.sports for a in athletes}
    
    if request.method == 'POST':
        form = TrainingSessionForm(request.POST)
        form.fields['athlete'].queryset = athletes
        if form.is_valid():
            selected_athlete = form.cleaned_data.get('athlete')
            
            if selected_athlete:
                # Single Athlete selected
                session = form.save(commit=False)
                if is_coach:
                    session.sports = coach.sports
                    session.coach = coach
                session.save()
                
                # Notification logic for single athlete
                if not request.user.is_superuser:
                    coach_name = request.user.get_full_name() or request.user.username
                    athlete_name = session.athlete.user.get_full_name() or session.athlete.user.username
                    Notification.objects.create(
                        title="New Training Session Scheduled",
                        message=f"Coach {coach_name} scheduled a training session for {athlete_name} on {session.session_date}.",
                        notification_type='session'
                    )
            else:
                # "All Athletes" selected (athlete field is None)
                for athlete in athletes:
                    session = TrainingSession.objects.create(
                        athlete=athlete,
                        coach=coach if is_coach else None,
                        session_date=form.cleaned_data['session_date'],
                        duration_minutes=form.cleaned_data['duration_minutes'],
                        notes=form.cleaned_data['notes'],
                        status=form.cleaned_data['status'],
                        sports=coach.sports if is_coach else form.cleaned_data.get('sports_selection', '')
                    )
                    
                    # Create notification for each athlete
                    if not request.user.is_superuser:
                        coach_name = request.user.get_full_name() or request.user.username
                        Notification.objects.create(
                            title="Team Training Session Scheduled",
                            message=f"Coach {coach_name} scheduled a team session for {athlete.user.username} on {session.session_date}.",
                            notification_type='session'
                        )
                
                messages.success(request, f"Training session scheduled for all {athletes.count()} athletes.")
                
            return redirect('management:training_session_list')
    else:
        form = TrainingSessionForm()
        form.fields['athlete'].queryset = athletes
        if is_coach:
            del form.fields['sports_selection']

    return render(request, 'management/training_session_form.html', {
        'form': form,
        'athlete_sports_map': athlete_sports_map
    })

@login_required
def training_session_update(request, pk):
    session = get_object_or_404(TrainingSession, pk=pk)
    is_coach = Coach.objects.filter(user=request.user).exists()
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athletes = Athlete.objects.filter(sports__in=coach_sports)
    else:
        athletes = Athlete.objects.all()

    athlete_sports_map = {str(a.id): a.sports for a in athletes}
    
    if request.method == 'POST':
        form = TrainingSessionForm(request.POST, instance=session)
        form.fields['athlete'].queryset = athletes
        if form.is_valid():
            session = form.save(commit=False)
            if is_coach:
                session.sports = coach.sports
            session.save()
            return redirect('management:training_session_list')
    else:
        form = TrainingSessionForm(instance=session)
        form.fields['athlete'].queryset = athletes
        if is_coach:
            del form.fields['sports_selection']

    return render(request, 'management/training_session_form.html', {
        'form': form,
        'athlete_sports_map': athlete_sports_map
    })

@login_required
def training_session_delete(request, pk):
    session = get_object_or_404(TrainingSession, pk=pk)
    if request.method == 'POST':
        session.delete()
        return redirect('management:training_session_list')
    return render(request, 'management/training_session_confirm_delete.html', {'session': session})

@login_required
def generate_report(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="athlete_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Username', 'Contact Number', 'Address'])

    athletes = Athlete.objects.all()
    for athlete in athletes:
        writer.writerow([athlete.user.username, athlete.contact_number, athlete.address])

    return response

@login_required
def dashboard(request):
    # Check if user is an athlete
    athlete = Athlete.objects.filter(user=request.user).first()
    if athlete:
        return redirect('management:athlete_dashboard')
    
    # Check if user is a coach
    coach = Coach.objects.filter(user=request.user).first()
    if coach:
        sports_val = str(coach.sports or "").lower()
        if any(s in sports_val for s in ['basketball', 'volleyball', 'sepak takraw']):
            return sport_coach_dashboard(request, coach)
        return render_coach_dashboard(request, coach)
    
    # If not an athlete, coach, or superuser, redirect to portal registration
    if not request.user.is_superuser:
        return redirect('management:register_athlete')
        
    # Admin Dashboard View
    return render_admin_dashboard(request)

@login_required
def sport_coach_dashboard(request, coach):
    # Determine the primary sport for this dashboard
    current_sport = 'Basketball' # Default
    sports_val = str(coach.sports or "").lower()
    if 'volleyball' in sports_val: current_sport = 'Volleyball'
    elif 'sepak takraw' in sports_val: current_sport = 'Sepak Takraw'
    
    # Requirement 1: Summary Cards
    athletes = Athlete.objects.filter(sports__icontains=current_sport)
    athletes_count = athletes.count()
    
    sessions = TrainingSession.objects.filter(sports__icontains=current_sport).order_by('-session_date')
    active_sessions_count = sessions.filter(status='Scheduled').count()
    
    # Requirement 7: Team Summary
    team = Team.objects.filter(coach=coach, sport=current_sport).first()
    if not team:
        # Auto-create a team record if it doesn't exist
        team = Team.objects.create(name=f"{coach.user.username}'s Team", coach=coach, sport=current_sport)
    
    # Recalculate team wins/losses based on ALL individual GameRecords for this sport's athletes
    team_wins = GameRecord.objects.filter(athlete__in=athletes, win=True).count()
    team_losses = GameRecord.objects.filter(athlete__in=athletes, win=False).count()
    
    # Update team object for the win_loss_ratio calculation in template
    team.wins = team_wins
    team.losses = team_losses
    # Note: We don't necessarily need to save to DB here if we just want it for the current render, 
    # but saving keeps the Team model in sync.
    team.save()
    
    # Calculate Team Averages
    perf_records = PerformanceRecord.objects.filter(athlete__in=athletes)
    
    # Recalculate BasketballStat totals from GameRecords to ensure accuracy
    for athlete in athletes:
        stat, _ = BasketballStat.objects.get_or_create(athlete=athlete)
        game_totals = GameRecord.objects.filter(athlete=athlete).aggregate(
            t_pts=Sum('points'),
            t_ast=Sum('assists'),
            t_reb=Sum('rebounds')
        )
        stat.points = game_totals['t_pts'] or 0
        stat.assists = game_totals['t_ast'] or 0
        stat.rebounds = game_totals['t_reb'] or 0
        stat.save()

    # Sport-specific metrics
    if current_sport == 'Basketball':
        metrics = ['Points', 'Assists', 'Rebounds', 'Speed']
        core_m1, core_m2 = 'Field Goal %', '3-Point Accuracy'
    elif current_sport == 'Volleyball':
        metrics = ['Aces', 'Kills', 'Blocks', 'Digs']
        core_m1, core_m2 = 'Attack Success %', 'Service Accuracy'
    else: # Sepak Takraw
        metrics = ['Spikes', 'Serves', 'Blocks', 'Agility']
        core_m1, core_m2 = 'Spike Success %', 'Serve Accuracy'
        
    team_averages = {}
    for m in metrics:
        values = []
        for r in perf_records.filter(metric__icontains=m):
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(r.value))
            if nums: values.append(float(nums[0]))
        team_averages[m] = round(sum(values)/len(values), 1) if values else 0

    # Top Performer / Athlete Needing Attention (Dynamic calculation based on core metrics and game records)
    athlete_performance = []
    for a in athletes:
        # Use exact metric names for accuracy
        m1 = PerformanceRecord.objects.filter(athlete=a, metric=core_m1).order_by('-record_date', '-id').first()
        m2 = PerformanceRecord.objects.filter(athlete=a, metric=core_m2).order_by('-record_date', '-id').first()
        att = PerformanceRecord.objects.filter(athlete=a, metric='Attendance Consistency').order_by('-record_date', '-id').first()
        
        # Extract numeric values using regex
        def get_val(record):
            if not record: return 0
            # Ensure we only get the number part
            try:
                nums = re.findall(r"(\d+)", str(record.value))
                return int(nums[0]) if nums else 0
            except (ValueError, TypeError):
                return 0

        m1_val = get_val(m1)
        m2_val = get_val(m2)
        att_val = get_val(att)
        
        # Calculate score from performance records
        avg_score = (m1_val + m2_val + att_val) / 3.0
        
        # Get actual performance trend 
        latest_eval = Evaluation.objects.filter(athlete=a).order_by("-date").first()
        trend_val = getattr(latest_eval, 'speed_trend', 'Stable')

        # Check Attendance directly for "Intervention Needed" logic (matches compliance dashboard)
        att_qs = Attendance.objects.filter(athlete=a)
        missed_sessions = att_qs.filter(status='Absent').count()
        if att_qs.count() == 0:
            missed_sessions = TrainingSession.objects.filter(athlete=a, status='Missed').count()
        
        requires_attention = missed_sessions >= 10

        athlete_performance.append({
            'athlete': a, 
            'score': avg_score,
            'id': a.id, # tie-breaker
            'trend': trend_val,
            'requires_attention': requires_attention,
            'missed': missed_sessions
        })
    
    # Sort by score descending, then by ID to ensure stable selection
    athlete_performance.sort(key=lambda x: (x['score'], -x['id']), reverse=True)
    
    # Final selection
    top_athlete = None
    top_athlete_trend = "Stable"
    needs_attention = None
    
    # Needs attention based ONLY on specific bad criteria: >= 10 missed practices
    if athlete_performance:
        bad_athletes = [p for p in athlete_performance if p['requires_attention']]
        if bad_athletes:
            # Get the ONE with the MOST missed sessions
            bad_athletes.sort(key=lambda x: x['missed'], reverse=True)
            needs_attention = bad_athletes[0]['athlete']

    # CRITICAL FIX: Top Performer must mirror the Basketball Analytics MVP logic (which relies on Game Records)
    # to ensure consistency across the entire application.
    b_stats = BasketballStat.objects.filter(athlete__in=athletes)
    if b_stats.exists():
        top_stat = max(b_stats, key=lambda s: s.overall_rating(), default=None)
        if top_stat:
            top_athlete = top_stat.athlete
            # Fetch the actual trend for this newly selected top athlete
            latest_eval = Evaluation.objects.filter(athlete=top_athlete).order_by("-date").first()
            top_athlete_trend = getattr(latest_eval, 'speed_trend', 'Stable')

    # Fallback if no game records exist
    if not top_athlete and athlete_performance:
        top_athlete = athlete_performance[0]['athlete']
        top_athlete_trend = athlete_performance[0]['trend']

    # Sport-specific labels for averages
    if current_sport == 'Basketball':
        l1, l2, l3 = 'Points', 'Assists', 'Rebounds'
    elif current_sport == 'Volleyball':
        l1, l2, l3 = 'Aces', 'Kills', 'Blocks'
    else:
        l1, l2, l3 = 'Spikes', 'Serves', 'Blocks'

    b_stats = BasketballStat.objects.filter(athlete__in=athletes)
    count = b_stats.count()
    if count > 0:
        team_averages[l1] = round(sum(s.points for s in b_stats) / count, 1)
        team_averages[l2] = round(sum(s.assists for s in b_stats) / count, 1)
        team_averages[l3] = round(sum(s.rebounds for s in b_stats) / count, 1)
        team_averages['Speed' if current_sport == 'Basketball' else 'Digs' if current_sport == 'Volleyball' else 'Agility'] = round(sum(float(s.speed) for s in b_stats) / count, 1)
    else:
        team_averages[l1] = team_averages[l2] = team_averages[l3] = 0

    # Replace top_athlete with one from BasketballStat
    # (Removed to allow dynamic core metrics PerformanceRecord logic to take precedence)

    top_athlete_stats = None
    if top_athlete:
        # Get labels for display
        if current_sport == 'Basketball':
            label1, label2 = 'Field Goal %', '3-Point Accuracy'
        elif current_sport == 'Volleyball':
            label1, label2 = 'Attack Success %', 'Service Accuracy'
        else: # Sepak Takraw
            label1, label2 = 'Spike Success %', 'Serve Accuracy'

        # Use exact match for fetching top performer stats too
        m1_record = PerformanceRecord.objects.filter(athlete=top_athlete, metric=core_m1).order_by('-record_date', '-id').first()
        m2_record = PerformanceRecord.objects.filter(athlete=top_athlete, metric=core_m2).order_by('-record_date', '-id').first()
        
        # Physical Conditioning
        sprint_record = PerformanceRecord.objects.filter(athlete=top_athlete, metric__icontains='Sprint').order_by('-record_date', '-id').first()
        leap_record = PerformanceRecord.objects.filter(athlete=top_athlete, metric__icontains='Leap').order_by('-record_date', '-id').first()
        agility_record = PerformanceRecord.objects.filter(athlete=top_athlete, metric__icontains='Agility').order_by('-record_date', '-id').first()
        
        # Attendance Rate
        # Check if manual override exists
        attendance_record = PerformanceRecord.objects.filter(athlete=top_athlete, metric='Attendance Consistency').order_by('-record_date', '-id').first()
        if attendance_record:
            attendance_rate = int(attendance_record.value)
        else:
            total_sessions = TrainingSession.objects.filter(athlete=top_athlete).count()
            completed_sessions = TrainingSession.objects.filter(athlete=top_athlete, status='Completed').count()
            attendance_rate = round((completed_sessions / total_sessions * 100)) if total_sessions > 0 else 0

        # Coach's Evaluation
        latest_eval = Evaluation.objects.filter(athlete=top_athlete).order_by('-date').first()
        
        # Practice Consistency
        recent_sessions = TrainingSession.objects.filter(athlete=top_athlete).order_by('-session_date')[:4]
        
        # Mocking some details for the look in the image
        positions = {
            'Basketball': 'Point Guard',
            'Volleyball': 'Outside Hitter',
            'Sepak Takraw': 'Tekong'
        }

        top_athlete_stats = {
            'm1_val': re.findall(r"\d+", str(m1_record.value))[0] if m1_record and re.findall(r"\d+", str(m1_record.value)) else "0",
            'm2_val': re.findall(r"\d+", str(m2_record.value))[0] if m2_record and re.findall(r"\d+", str(m2_record.value)) else "0",
            'm1_label': label1,
            'm2_label': label2,
            'sprint_time': sprint_record.value if sprint_record else "0",
            'vertical_leap': leap_record.value if leap_record else "0",
            'agility_score': agility_record.value if agility_record else "0",
            'attendance_rate': attendance_rate,
            'evaluation': latest_eval.notes if latest_eval else "Demonstrating exceptional growth and leadership on the court. Focus remains on consistency.",
            'sessions': recent_sessions,
            'position': top_athlete.position if top_athlete and top_athlete.position else positions.get(current_sport, 'Athlete'),
            'jersey_no': top_athlete.jersey_number if top_athlete and top_athlete.jersey_number else '#--',
            'year': top_athlete.grade_level if top_athlete and top_athlete.grade_level else 'Active'
        }
        
        # (Removed b_state override for top_athlete_stats to show the actual core metrics instead of GameRecord points globally)

    # Requirement 3 & 8: Performance Monitoring & Comparison
    athlete1_id = request.GET.get('athlete1')
    athlete2_id = request.GET.get('athlete2')
    comparison_data = None
    if athlete1_id and athlete2_id:
        a1 = athletes.filter(id=athlete1_id).first()
        a2 = athletes.filter(id=athlete2_id).first()
        if a1 and a2:
            comparison_data = {
                'athlete1': a1,
                'athlete2': a2,
                'metrics': []
            }
            for m in metrics:
                v1 = PerformanceRecord.objects.filter(athlete=a1, metric__icontains=m).order_by('-record_date').first()
                v2 = PerformanceRecord.objects.filter(athlete=a2, metric__icontains=m).order_by('-record_date').first()
                comparison_data['metrics'].append({
                    'name': m,
                    'v1': v1.value if v1 else 0,
                    'v2': v2.value if v2 else 0
                })

    # Requirement 4: Activity Feed
    recent_athlete_logs = PerformanceRecord.objects.filter(athlete__in=athletes).order_by('-record_date')[:5]
    
    activity_feed = []
    sport_icon = 'fa-basketball-ball'
    if current_sport == 'Volleyball': sport_icon = 'fa-volleyball-ball'
    elif current_sport == 'Sepak Takraw': sport_icon = 'fa-circle-notch'
    
    for log in recent_athlete_logs:
        activity_feed.append({
            'detail': f"logged {log.metric}: {log.value}",
            'athlete': log.athlete.user.username,
            'date': log.record_date,
            'status': 'improving' if any(keyword in log.metric.lower() for keyword in ['points', 'kills', 'spikes']) else 'stable',
            'icon': sport_icon
        })
    activity_feed.sort(key=lambda x: x['date'], reverse=True)

    # Team Alerts: live injury + attendance alerts
    injured_athletes = []
    for athlete in athletes:
        injury_status = (athlete.injury_status or '').strip()
        if injury_status and injury_status.lower() not in {'none', 'n/a', 'no'}:
            injured_athletes.append({
                'id': athlete.id,
                'name': athlete.user.get_full_name() or athlete.user.username,
                'status': injury_status,
            })

    attendance_alerts = []
    for athlete in athletes:
        att_qs = Attendance.objects.filter(athlete=athlete)
        total_sessions = att_qs.count()
        missed_sessions = att_qs.filter(status='Absent').count()
        if total_sessions == 0:
            total_sessions = TrainingSession.objects.filter(athlete=athlete).exclude(status='Scheduled').count()
            missed_sessions = TrainingSession.objects.filter(athlete=athlete, status='Missed').count()

        if missed_sessions > 0:
            attendance_rate = round(((total_sessions - missed_sessions) / total_sessions) * 100, 1) if total_sessions else 100.0
            attendance_alerts.append({
                'id': athlete.id,
                'name': athlete.user.get_full_name() or athlete.user.username,
                'missed_sessions': int(missed_sessions),
                'total_sessions': int(total_sessions),
                'attendance_rate': attendance_rate,
            })

    attendance_alerts.sort(key=lambda item: (item['missed_sessions'], -item['attendance_rate']), reverse=True)
    attendance_alert_count = len(attendance_alerts)

    team_alerts = {
        'injury_count': len(injured_athletes),
        'injured_athletes': injured_athletes[:6],
        'attendance_count': attendance_alert_count,
        'attendance_athletes': attendance_alerts[:6],
        'critical_attendance_count': sum(1 for item in attendance_alerts if item['missed_sessions'] >= 3),
    }

    # Requirement 10: Announcements
    announcements = Announcement.objects.filter(coach=coach, sport=current_sport).order_by('-created_at')[:3]

    roster_user_ids = list(athletes.values_list("user_id", flat=True))
    coach_unread_messages_count = (
        Message.objects.filter(
            receiver=coach.user,
            sender_id__in=roster_user_ids,
            is_read=False,
        ).count()
        if roster_user_ids
        else 0
    )

    chart_payload = build_interactive_performance_chart_data(perf_records, current_sport, athletes=athletes)

    context = {
        'coach': coach,
        'team': team,
        'athletes': athletes,
        'athletes_count': athletes_count,
        'active_sessions_count': active_sessions_count,
        'team_averages': team_averages,
        'top_athlete': top_athlete,
        'top_athlete_stats': top_athlete_stats,
        'top_athlete_trend': top_athlete_trend,
        'needs_attention': needs_attention,
        'activity_feed': activity_feed,
        'comparison_data': comparison_data,
        'announcements': announcements,
        'team_alerts': team_alerts,
        'chart_data_json': json.dumps(chart_payload) if chart_payload else None,
        'portal_type': 'coach',
        'in_portal': True,
        'is_coach_dashboard': True,
        'coach_sport': current_sport,
        'today': timezone.now(),
        'coach_unread_messages_count': coach_unread_messages_count,
    }
    return render(request, 'management/sport_coach_dashboard.html', context)

def render_admin_dashboard(request):
    athletes_count = Athlete.objects.count()
    sessions_count = TrainingSession.objects.count()
    payments_total = sum(p.amount for p in Payment.objects.all())
    performance_data = PerformanceRecord.objects.all()
    
    # Notifications for admin
    unread_notifications = Notification.objects.filter(is_read=False).order_by('-created_at')[:5]
    all_recent_notifications = Notification.objects.all().order_by('-created_at')[:10]
    unread_notifications_count = Notification.objects.filter(is_read=False).count()
    
    # Check for unread sessions and payments specifically for the pulsing alerts
    has_unread_payments = Notification.objects.filter(is_read=False, notification_type='payment').exists()
    has_unread_sessions = Notification.objects.filter(is_read=False, notification_type='session').exists()

    static_chart = generate_performance_chart(performance_data, "Global Performance Over Time")
    interactive_chart_data = get_performance_chart_data(performance_data)

    context = {
        'athletes_count': athletes_count,
        'sessions_count': sessions_count,
        'payments_total': payments_total,
        'chart': static_chart,
        'chart_data_json': json.dumps(interactive_chart_data) if interactive_chart_data else None,
        'notifications': unread_notifications,
        'all_recent_notifications': all_recent_notifications,
        'unread_notifications_count': unread_notifications_count,
        'has_unread_payments': has_unread_payments,
        'has_unread_sessions': has_unread_sessions,
        'is_athlete': False,
        'portal_type': 'admin',
        'in_portal': True
    }
    return render(request, 'management/dashboard.html', context)

@login_required
def mark_notification_read(request, pk):
    if not request.user.is_superuser:
        return redirect('home')
    notification = get_object_or_404(Notification, pk=pk)
    notification.is_read = True
    notification.save()
    return redirect('management:dashboard')

@login_required
def mark_all_notifications_read(request):
    if not request.user.is_superuser:
        return HttpResponse(status=403)
    Notification.objects.filter(is_read=False).update(is_read=True)
    return HttpResponse(status=200)

@login_required
def notification_history(request):
    if not request.user.is_superuser:
        return redirect('home')
    notifications = Notification.objects.all().order_by('-created_at')
    return render(request, 'management/notification_history.html', {
        'notifications': notifications,
        'portal_type': 'admin',
        'in_portal': True
    })

def generate_performance_chart(performance_data, title):
    df = pd.DataFrame(list(performance_data.values('record_date', 'metric', 'value')))
    chart = None
    if not df.empty:
        try:
            df['record_date'] = pd.to_datetime(df['record_date'])
            # Convert values to numeric, turning non-numeric strings (like "25.5s") into NaN
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            # Drop rows where value conversion failed (NaN)
            df = df.dropna(subset=['value'])
            
            if not df.empty:
                pivot_df = df.pivot(index='record_date', columns='metric', values='value')
                plt.figure(figsize=(10, 6))
                pivot_df.plot(kind='line')
                plt.title(title)
                plt.xlabel('Date')
                plt.ylabel('Value')
                buffer = io.BytesIO()
                plt.savefig(buffer, format='png')
                buffer.seek(0)
                chart = base64.b64encode(buffer.getvalue()).decode('utf-8')
                plt.close()
        except Exception:
            # Fallback for any unexpected errors during processing
            plt.close()
    return chart

def _sport_coaches_queryset(current_sport):
    """Coaches for this sport; ordered by pk so .first() is stable."""
    return Coach.objects.filter(sports__icontains=current_sport).select_related("user").order_by("pk")


def _athlete_sport_labels(athlete):
    """Canonical sport labels for this athlete (matches athlete_dashboard logic)."""
    s = str(athlete.sports or "").lower()
    labels = []
    if "volleyball" in s:
        labels.append("Volleyball")
    if "sepak" in s or "takraw" in s:
        labels.append("Sepak Takraw")
    if "basketball" in s:
        labels.append("Basketball")
    if not labels:
        labels.append("Basketball")
    seen = set()
    out = []
    for L in labels:
        if L not in seen:
            seen.add(L)
            out.append(L)
    return out


def _allowed_coach_user_ids_for_athlete(athlete):
    ids = set()
    for sport in _athlete_sport_labels(athlete):
        for c in _sport_coaches_queryset(sport):
            ids.add(c.user_id)
    return ids


def _coaches_portal_payload(athlete, request, unread_msgs_by_sender=None):
    """Coaches across all of the athlete's sports (for Coach Discovery UI)."""
    if unread_msgs_by_sender is None:
        unread_msgs_by_sender = {}
    by_coach_pk = {}
    for sport in _athlete_sport_labels(athlete):
        for c in _sport_coaches_queryset(sport):
            if c.pk not in by_coach_pk:
                try:
                    if c.profile_picture:
                        av = request.build_absolute_uri(c.profile_picture.url)
                    else:
                        av = (
                            "https://api.dicebear.com/7.x/avataaars/svg?"
                            f"seed={c.user.username}"
                        )
                except Exception:
                    av = (
                        "https://api.dicebear.com/7.x/avataaars/svg?"
                        f"seed={c.user.username}"
                    )
                by_coach_pk[c.pk] = {
                    "id": c.pk,
                    "user_id": c.user_id,
                    "name": c.user.get_full_name() or c.user.username,
                    "specialization": (c.specialization or "").strip(),
                    "sports": [],
                    "avatar_url": av,
                    "unread_count": unread_msgs_by_sender.get(c.user_id, 0),
                }
            if sport not in by_coach_pk[c.pk]["sports"]:
                by_coach_pk[c.pk]["sports"].append(sport)
    rows = list(by_coach_pk.values())
    rows.sort(key=lambda r: (r["name"].lower(), r["id"]))
    return rows


def _coach_dm_threads_json(athlete, request_user):
    allowed = _allowed_coach_user_ids_for_athlete(athlete)
    out = {}
    for uid in sorted(allowed):
        msgs = Message.objects.filter(
            Q(sender=request_user, receiver_id=uid)
            | Q(receiver=request_user, sender_id=uid)
        ).order_by("timestamp")
        out[str(uid)] = [
            {
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
                "is_mine": m.sender_id == request_user.id,
            }
            for m in msgs
        ]
    return json.dumps(out)


def _coach_covers_sport(coach_obj, current_sport):
    if not coach_obj:
        return False
    return current_sport.lower() in (coach_obj.sports or "").lower()


def _resolve_primary_coach_for_athlete(athlete, current_sport):
    """
    Coach used for athlete→coach sends. Prefer latest session coach, then latest
    evaluation author, else first coach for the sport (by pk).
    """
    qs = _sport_coaches_queryset(current_sport)
    if not qs.exists():
        return None

    sessions = (
        TrainingSession.objects.filter(athlete=athlete, coach__isnull=False)
        .select_related("coach", "coach__user")
        .order_by("-session_date")[:25]
    )
    for s in sessions:
        if s.coach and _coach_covers_sport(s.coach, current_sport):
            return s.coach

    last_ev = (
        athlete.evaluations.select_related("coach")
        .order_by("-date")
        .first()
    )
    if last_ev and last_ev.coach_id:
        c = Coach.objects.filter(user_id=last_ev.coach_id).first()
        if c and _coach_covers_sport(c, current_sport):
            return c

    return qs.first()


@login_required
def athlete_dashboard(request):
    # Check if user is an athlete
    athlete = Athlete.objects.filter(user=request.user).first()
    if not athlete:
        # If no athlete profile exists, redirect to registration
        if not request.user.is_superuser and not Coach.objects.filter(user=request.user).exists():
            return redirect('management:register_athlete')
        return redirect('home')
    
    # Identify primary sport
    athlete_sports = str(athlete.sports or "").lower()
    if 'volleyball' in athlete_sports:
        current_sport = 'Volleyball'
    elif 'sepak takraw' in athlete_sports:
        current_sport = 'Sepak Takraw'
    else:
        current_sport = 'Basketball'

    unread_msgs_by_sender = dict(
        Message.objects.filter(receiver=request.user, is_read=False)
        .values_list("sender_id")
        .annotate(c=Count("id"))
    )

    # Sport-specific labels and icons
    if current_sport == 'Basketball':
        stat_labels = {'l1': 'Points', 'l2': 'Assists', 'l3': 'Rebounds'}
        tm_labels = {'l1_short': 'PTS', 'l2_short': 'AST', 'l3_short': 'REB', 'l4_short': 'BLK', 'l1': 'PTS', 'l2': 'AST', 'l3': 'REB', 'l4': 'BLK'}
        radar_categories = ['SPEED', 'STAMINA', 'SHOOTING', 'DEFENSE', 'AGILITY', 'REBOUNDS']
        sport_icon = 'basketball'
    elif current_sport == 'Volleyball':
        stat_labels = {'l1': 'Aces', 'l2': 'Kills', 'l3': 'Blocks'}
        tm_labels = {'l1_short': 'ACE', 'l2_short': 'KIL', 'l3_short': 'BLK', 'l4_short': 'DIG', 'l1': 'ACES', 'l2': 'KILLS', 'l3': 'BLOCKS', 'l4': 'DIGS'}
        radar_categories = ['SPEED', 'STAMINA', 'SPIKING', 'SERVING', 'AGILITY', 'BLOCKING']
        sport_icon = 'volleyball'
    else: # Sepak Takraw
        stat_labels = {'l1': 'Spikes', 'l2': 'Serves', 'l3': 'Blocks'}
        tm_labels = {'l1_short': 'SPK', 'l2_short': 'SRV', 'l3_short': 'BLK', 'l4_short': 'DEF', 'l1': 'SPIKES', 'l2': 'SERVES', 'l3': 'BLOCKS', 'l4': 'DEFENSE'}
        radar_categories = ['SPEED', 'STAMINA', 'SPIKING', 'SERVING', 'AGILITY', 'BLOCKING']
        sport_icon = 'circle-dashed'

    # Handle new performance record submission
    if request.method == 'POST' and 'log_performance' in request.POST:
        perf_form = PerformanceRecordForm(request.POST)
        if perf_form.is_valid():
            perf = perf_form.save(commit=False)
            perf.athlete = athlete
            perf.save()
            return redirect('management:athlete_dashboard')
    elif request.method == 'POST' and 'send_teammate_message' in request.POST:
        content = (request.POST.get('teammate_message_content') or "").strip()
        rid = request.POST.get('receiver_user_id')
        perf_form = PerformanceRecordForm()
        if content and rid:
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                rid_int = None
            if rid_int and rid_int != request.user.id:
                allowed = Athlete.objects.filter(
                    sports__icontains=current_sport
                ).exclude(pk=athlete.pk).filter(user_id=rid_int).exists()
                if allowed:
                    other = User.objects.filter(pk=rid_int).first()
                    if other:
                        Message.objects.create(
                            sender=request.user, receiver=other, content=content
                        )
                        return redirect(
                            f"{request.path}?teammate_chat={rid_int}"
                        )
    elif request.method == 'POST' and 'send_message' in request.POST:
        content = (request.POST.get("message_content") or "").strip()
        allowed_coach_uids = _allowed_coach_user_ids_for_athlete(athlete)
        raw_target = request.POST.get("receiver_coach_user_id")
        coach = None
        if raw_target:
            try:
                tid = int(raw_target)
            except (TypeError, ValueError):
                tid = None
            if tid in allowed_coach_uids:
                coach = Coach.objects.filter(user_id=tid).select_related("user").first()
        if not coach:
            coach = _resolve_primary_coach_for_athlete(athlete, current_sport)
        if coach and content:
            Message.objects.create(
                sender=request.user, receiver=coach.user, content=content
            )
            Message.objects.filter(
                receiver=request.user,
                sender_id__in=allowed_coach_uids,
                is_read=False,
            ).update(is_read=True)
            if raw_target and str(coach.user_id) == str(raw_target).strip():
                return redirect(
                    f"{request.path}?coach_chat={coach.user_id}"
                )
            return redirect("management:athlete_dashboard")
        perf_form = PerformanceRecordForm()
    else:
        perf_form = PerformanceRecordForm()
    
    # Athlete Dashboard View
    sessions = TrainingSession.objects.filter(athlete=athlete).order_by('-session_date')[:5]
    payments = Payment.objects.filter(athlete=athlete).order_by('-payment_date')[:5]
    performance_data = PerformanceRecord.objects.filter(athlete=athlete)
    game_records = GameRecord.objects.filter(athlete=athlete).order_by('-date')[:10]
    
    # Radar Chart Data (Mocking some values if not in PerformanceRecord)
    stat, _ = BasketballStat.objects.get_or_create(athlete=athlete)
    
    # Helper to get latest metric value
    def get_latest_metric(metric_name):
        record = performance_data.filter(metric__icontains=metric_name).order_by('-record_date').first()
        if record:
            try:
                nums = re.findall(r"\d+", str(record.value))
                return int(nums[0]) if nums else 50
            except (ValueError, IndexError):
                return 50
        return 50

    if current_sport == 'Basketball':
        radar_values = [
            float(stat.speed) * 10 if float(stat.speed) < 10 else float(stat.speed), # Speed
            get_latest_metric('Attendance') or 75, # Stamina
            get_latest_metric('Field Goal') or 80, # Shooting
            70, # Defense (Mock)
            85, # Agility (Mock)
            get_latest_metric('Rebounds') or 65  # Rebounds (Mock)
        ]
    elif current_sport == 'Volleyball':
        radar_values = [
            float(stat.speed) * 10 if float(stat.speed) < 10 else float(stat.speed), # Speed
            75, # Stamina
            get_latest_metric('Attack Success') or 80, # Spiking
            get_latest_metric('Service Accuracy') or 85, # Serving
            90, # Agility (Mock)
            70  # Blocking (Mock)
        ]
    else: # Sepak Takraw
        radar_values = [
            float(stat.speed) * 10 if float(stat.speed) < 10 else float(stat.speed), # Speed
            75, # Stamina
            get_latest_metric('Spike Success') or 80, # Spiking
            get_latest_metric('Serve Accuracy') or 85, # Serving
            90, # Agility (Mock)
            70  # Blocking (Mock)
        ]
    
    # Activity Feed: Show what coaches have recorded for this athlete
    recent_coach_evaluations = athlete.evaluations.all().order_by('-date')[:5]
    recent_sessions = TrainingSession.objects.filter(athlete=athlete).order_by('-session_date')[:5]
    
    activity_feed = []
    for eval in recent_coach_evaluations:
        activity_feed.append({
            'type': 'evaluation',
            'detail': f"Coach {eval.coach.get_full_name() or eval.coach.username} added an evaluation" if eval.coach else "Coach added an evaluation",
            'notes': eval.notes,
            'date': eval.date,
            'icon': 'fa-clipboard-check',
            'color': 'text-success'
        })
    for session in recent_sessions:
        activity_feed.append({
            'type': 'session',
            'detail': f"Coach scheduled a {session.sports} session",
            'date': session.session_date.date(),
            'icon': 'fa-calendar-alt',
            'color': 'text-primary'
        })
    
    activity_feed.sort(key=lambda x: x['date'], reverse=True)
    activity_feed = activity_feed[:8]

    # Calculate season totals
    totals = game_records.aggregate(
        t1=Sum('points'),
        t2=Sum('assists'),
        t3=Sum('rebounds')
    )

    # Next upcoming practice / game for this athlete
    next_session = (
        TrainingSession.objects.filter(athlete=athlete, status="Scheduled")
        .order_by("session_date")
        .first()
    )

    # Team Discovery: teammates in same sport (excluding self), with stats + mock-friendly DNA
    roles_cycle = [
        "Point Guard",
        "Shooting Guard",
        "Small Forward",
        "Power Forward",
        "Center",
    ]
    teammate_athletes = (
        Athlete.objects.filter(sports__icontains=current_sport)
        .exclude(pk=athlete.pk)
        .select_related("user")
        .order_by("user__username")[:40]
    )
    teammates_portal = []
    for idx, ta in enumerate(teammate_athletes):
        tstat, _ = BasketballStat.objects.get_or_create(athlete=ta)
        t_games = GameRecord.objects.filter(athlete=ta)
        gc = t_games.count()
        agg = t_games.aggregate(
            pts_sum=Sum("points"),
            ast_sum=Sum("assists"),
            reb_sum=Sum("rebounds"),
        )
        total_pts = agg["pts_sum"] or 0
        total_ast = agg["ast_sum"] or 0
        total_reb = agg["reb_sum"] or 0
        if gc:
            ppg = round(total_pts / gc, 1)
            apg = round(total_ast / gc, 1)
            rpg = round(total_reb / gc, 1)
        else:
            ppg = round(max(0.0, float(tstat.points)) / 10.0, 1) or 0.0
            apg = round(max(0.0, float(tstat.assists)) / 10.0, 1) or 0.0
            rpg = round(max(0.0, float(tstat.rebounds)) / 10.0, 1) or 0.0
        bpg = round(1.0 + (idx % 4) * 0.3, 1)

        history = []
        for g in t_games.order_by("-date")[:8]:
            history.append(
                {
                    "opponent": g.opponent,
                    "timeline": g.date.strftime("%b %d, %Y"),
                    "pts": g.points,
                    "ast": g.assists,
                    "reb": g.rebounds,
                    "blk": min(6, g.rebounds // 4 + idx % 3),
                    "result": "WON" if g.win else "LOSS",
                }
            )
        if not history:
            history = [
                {
                    "opponent": "No games logged yet",
                    "timeline": "—",
                    "pts": "—",
                    "ast": "—",
                    "reb": "—",
                    "blk": "—",
                    "result": "—",
                }
            ]

        sp = float(tstat.speed)
        dna_object = {
            "speed": min(99, int(sp * 10) if sp < 12 else int(min(sp, 99))),
            "stamina": min(99, 70 + (idx * 3) % 25),
            "shooting": min(99, int(tstat.points) + 15),
            "defense": min(99, 60 + (idx * 7) % 35),
            "agility": min(99, int(tstat.assists) + 25),
            "rebounds": min(99, int(tstat.rebounds) + 20),
        }

        try:
            if ta.profile_picture:
                avatar_url = request.build_absolute_uri(ta.profile_picture.url)
            else:
                avatar_url = (
                    f"https://api.dicebear.com/7.x/avataaars/svg?seed={ta.user.username}"
                )
        except Exception:
            avatar_url = (
                f"https://api.dicebear.com/7.x/avataaars/svg?seed={ta.user.username}"
            )

        teammates_portal.append(
            {
                "id": ta.id,
                "user_id": ta.user_id,
                "name": ta.user.get_full_name() or ta.user.username,
                "number": ta.jersey_number if ta.jersey_number else "#--",
                "role": ta.position if ta.position else "Player",
                "avatar_url": avatar_url,
                "unread_count": unread_msgs_by_sender.get(ta.user_id, 0),
                "stats_object": {
                    "ppg": str(ppg),
                    "apg": str(apg),
                    "rpg": str(rpg),
                    "bpg": str(bpg),
                },
                "dna_object": dna_object,
                "history_array": history,
                "totals": {
                    "pts": int(total_pts),
                    "ast": int(total_ast),
                    "reb": int(total_reb),
                    "blk": 12 + (idx % 8),
                },
                "win_streak": min(5, gc) if gc else 0,
            }
        )

    allowed_coach_uids = _allowed_coach_user_ids_for_athlete(athlete)
    coach_user_ids = list(allowed_coach_uids)
    unread_coach_messages_count = (
        Message.objects.filter(
            receiver=request.user,
            sender_id__in=coach_user_ids,
            is_read=False,
        ).count()
        if coach_user_ids
        else 0
    )
    all_coach_rows = (
        Coach.objects.filter(user_id__in=allowed_coach_uids)
        .select_related("user")
        .order_by("pk")
    )
    coaches_by_user_id = {c.user_id: c for c in all_coach_rows}
    sport_coaches_count = len(coaches_by_user_id)
    coaches_portal = _coaches_portal_payload(athlete, request, unread_msgs_by_sender)
    coach_dm_threads_json = _coach_dm_threads_json(athlete, request.user)
    primary_coach_for_chat = _resolve_primary_coach_for_athlete(
        athlete, current_sport
    )

    tm_user_ids = list(teammate_athletes.values_list("user_id", flat=True))
    if coach_user_ids:
        chat_messages = (
            Message.objects.filter(
                Q(sender=request.user, receiver_id__in=coach_user_ids)
                | Q(receiver=request.user, sender_id__in=coach_user_ids)
            )
            .select_related("sender", "receiver")
            .order_by("timestamp")
        )
    else:
        chat_messages = Message.objects.none()

    coach_chat_thread = []
    for m in chat_messages:
        is_mine = m.sender_id == request.user.id
        coach_who_sent = (
            coaches_by_user_id.get(m.sender_id) if not is_mine else None
        )
        coach_chat_thread.append(
            {
                "message": m,
                "is_mine": is_mine,
                "coach": coach_who_sent,
            }
        )

    threads = defaultdict(list)
    if tm_user_ids:
        for m in (
            Message.objects.filter(
                Q(sender=request.user, receiver_id__in=tm_user_ids)
                | Q(receiver=request.user, sender_id__in=tm_user_ids)
            )
            .select_related("sender", "receiver")
            .order_by("timestamp")
        ):
            other_uid = (
                m.receiver_id if m.sender_id == request.user.id else m.sender_id
            )
            threads[other_uid].append(
                {
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "is_mine": m.sender_id == request.user.id,
                }
            )
    teammate_threads_json = json.dumps({str(k): v for k, v in threads.items()})

    athlete_evaluations = (
        athlete.evaluations.select_related("coach").order_by("-date")
    )
    athlete_incidents = (
        athlete.incidents.select_related("coach", "coach__user").order_by(
            "-date", "-created_at"
        )
    )
    athlete_goals_list = list(
        athlete.goals.all().order_by("-due_date", "title")[:12]
    )

    context = {
        "athlete": athlete,
        "sessions": sessions,
        "payments": payments,
        "game_records": game_records,
        "totals": totals,
        "coach_chat_thread": coach_chat_thread,
        "primary_coach_for_chat": primary_coach_for_chat,
        "sport_coaches_count": sport_coaches_count,
        "coaches_portal_json": json.dumps(coaches_portal),
        "coach_dm_threads_json": coach_dm_threads_json,
        "athlete_evaluations": athlete_evaluations,
        "athlete_incidents": athlete_incidents,
        "athlete_goals_list": athlete_goals_list,
        "teammate_threads_json": teammate_threads_json,
        "radar_categories": json.dumps(radar_categories),
        "radar_values": json.dumps(radar_values),
        "activity_feed": activity_feed,
        "stat_labels": stat_labels,
        "tm_labels": tm_labels,
        "sport_icon": sport_icon,
        "current_sport": current_sport,
        "is_athlete": True,
        "in_portal": True,
        "portal_type": "athlete",
        "perf_form": perf_form,
        "next_session": next_session,
        "teammates_portal": teammates_portal,
        "teammates_portal_json": json.dumps(teammates_portal),
        "unread_coach_messages_count": unread_coach_messages_count,
    }
    return render(request, "management/athlete_dashboard.html", context)


@login_required
def athlete_my_progress_report(request):
    """Printable progress summary for the logged-in athlete only."""
    athlete = Athlete.objects.filter(user=request.user).select_related("user").first()
    if not athlete:
        return redirect("home")

    athlete_sports = str(athlete.sports or "").lower()
    if "volleyball" in athlete_sports:
        current_sport = "Volleyball"
    elif "sepak takraw" in athlete_sports or "sepak" in athlete_sports:
        current_sport = "Sepak Takraw"
    else:
        current_sport = "Basketball"

    evaluations = athlete.evaluations.select_related("coach").order_by("-date")
    game_records = GameRecord.objects.filter(athlete=athlete).order_by("-date")[:40]
    goals = athlete.goals.all().order_by("status", "title")[:24]
    incidents = athlete.incidents.select_related("coach", "coach__user").order_by(
        "-date", "-created_at"
    )[:24]
    stat, _ = BasketballStat.objects.get_or_create(athlete=athlete)
    sessions_done = TrainingSession.objects.filter(
        athlete=athlete, status="Completed"
    ).count()

    if current_sport == 'Volleyball':
        stat_labels = {'l1': 'Aces', 'l2': 'Kills', 'l3': 'Blocks'}
    elif current_sport == 'Sepak Takraw':
        stat_labels = {'l1': 'Spikes', 'l2': 'Serves', 'l3': 'Blocks'}
    else:
        stat_labels = {'l1': 'Pts', 'l2': 'Ast', 'l3': 'Reb'}

    context = {
        "athlete": athlete,
        "current_sport": current_sport,
        "evaluations": evaluations,
        "game_records": game_records,
        "goals": goals,
        "incidents": incidents,
        "basketball_stat": stat,
        "sessions_completed": sessions_done,
        "today": timezone.now(),
        "stat_labels": stat_labels,
    }
    return render(
        request, "management/athlete_my_progress_report.html", context
    )


@login_required
def register_athlete(request):
    # Check if athlete record already exists
    if Athlete.objects.filter(user=request.user).exists():
        return redirect('management:athlete_dashboard')
    
    if request.method == 'POST':
        form = AthleteProfileForm(request.POST, request.FILES)
        if form.is_valid():
            athlete = form.save(commit=False)
            athlete.user = request.user
            athlete.save()
            # Handle profile picture upload during registration
            if 'profile_picture' in request.FILES:
                athlete.profile_picture = request.FILES['profile_picture']
                athlete.save()
            return redirect('management:athlete_dashboard')
    else:
        form = AthleteProfileForm()
    
    return render(request, 'management/athlete_form.html', {
        'form': form, 
        'is_registration': True,
        'in_portal': True,
        'portal_type': 'athlete',
        'is_athlete': False # Hide sidebar links during registration
    })

@login_required
def athlete_profile_update(request):
    athlete = get_object_or_404(Athlete, user=request.user)
    if request.method == 'POST':
        form = AthleteProfileForm(request.POST, request.FILES, instance=athlete)
        if form.is_valid():
            form.save()
            return redirect('management:athlete_dashboard')
    else:
        form = AthleteProfileForm(instance=athlete)
    return render(request, 'management/athlete_form.html', {
        'form': form, 
        'is_profile_update': True,
        'in_portal': True,
        'portal_type': 'athlete'
    })

@login_required
def athlete_list(request):
    sort_by = request.GET.get('sort_by', 'user__username')
    direction = request.GET.get('direction', 'asc')
    query = request.GET.get('query', '')

    is_coach = Coach.objects.filter(user=request.user).exists()
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athletes = Athlete.objects.filter(sports__in=coach_sports)
    else:
        athletes = Athlete.objects.all()

    if query:
        query_parts = query.split()
        search_filter = Q()
        for part in query_parts:
            search_filter |= (
                Q(user__username__icontains=part) |
                Q(user__first_name__icontains=part) |
                Q(user__last_name__icontains=part) |
                Q(contact_number__icontains=part) |
                Q(address__icontains=part) |
                Q(sports__icontains=part)
            )
        athletes = athletes.filter(search_filter)

    if direction == 'desc':
        sort_by = f'-{sort_by}'
    
    athletes = athletes.order_by(sort_by)

    return render(request, 'management/athlete_list.html', {'athletes': athletes})

@login_required
def athlete_detail(request, pk):
    # Allow superusers and coaches to view athlete details
    is_coach = Coach.objects.filter(user=request.user).exists()
    if not request.user.is_superuser and not is_coach:
        return redirect('home')
        
    athlete = get_object_or_404(Athlete, pk=pk)
    
    # If coach, ensure they only see athletes of their sport
    if is_coach:
        coach = Coach.objects.get(user=request.user)
        coach_sports = coach.sports.split(',') if coach.sports else []
        athlete_sports = athlete.sports.split(',') if athlete.sports else []
        # Check if there's an overlap
        if not any(sport in coach_sports for sport in athlete_sports):
            messages.error(request, "You do not have permission to view athletes from other sports.")
            return redirect('management:dashboard')
            
    return render(request, 'management/athlete_detail.html', {'athlete': athlete})

@login_required
def athlete_create(request):
    if not request.user.is_superuser:
        return redirect('home')
    if request.method == 'POST':
        form = AthleteForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('management:athlete_list')
    else:
        form = AthleteForm()
    return render(request, 'management/athlete_form.html', {'form': form})

@login_required
def athlete_update(request, pk):
    athlete = get_object_or_404(Athlete, pk=pk)
    user = athlete.user
    
    # Check if user is a coach
    is_coach = Coach.objects.filter(user=request.user).exists()
    if not request.user.is_superuser and not is_coach:
        return redirect('home')
        
    if request.method == 'POST':
        if request.user.is_superuser:
            user_form = UserCreationByAdminForm(request.POST, instance=user)
        else:
            user_form = UserUpdateByCoachForm(request.POST, instance=user)
            
        athlete_form = AthleteForm(request.POST, request.FILES, instance=athlete)
        
        if user_form.is_valid() and athlete_form.is_valid():
            # Save user without committing to avoid saving raw password if blank
            user = user_form.save(commit=False)
            
            # Only admin can change password
            if request.user.is_superuser:
                password = user_form.cleaned_data.get('password')
                if password:
                    user.set_password(password)
                    athlete.plain_password = password
            
            user.save()
            athlete_form.save()
            messages.success(request, f"Athlete {user.username} information updated successfully.")
            return redirect('management:athlete_detail', pk=pk)
    else:
        if request.user.is_superuser:
            # Pre-fill the password field with plain_password if it exists
            user_form = UserCreationByAdminForm(instance=user, initial={'password': athlete.plain_password})
        else:
            user_form = UserUpdateByCoachForm(instance=user)
        athlete_form = AthleteForm(instance=athlete)

    return render(request, 'management/admin_register_athlete.html', {
        'user_form': user_form,
        'athlete_form': athlete_form,
        'is_edit': True,
        'athlete': athlete
    })

@login_required
def athlete_delete(request, pk):
    if not request.user.is_superuser:
        return redirect('home')
    athlete = get_object_or_404(Athlete, pk=pk)
    if request.method == 'POST':
        athlete.delete()
        return redirect('management:athlete_list')
    return render(request, 'management/athlete_confirm_delete.html', {'athlete': athlete})

from django.http import JsonResponse
from datetime import date as date_obj

@login_required
def update_basketball_stats(request, athlete_id):
    if request.method == 'POST':
        athlete = get_object_or_404(Athlete, id=athlete_id)
        stat, created = BasketballStat.objects.get_or_create(athlete=athlete)
        
        try:
            # Check if this is a full game record update
            opponent = request.POST.get('opponent')
            if opponent:
                venue = request.POST.get('venue', 'Unknown')
                pts = int(request.POST.get('points', 0))
                ast = int(request.POST.get('assists', 0))
                reb = int(request.POST.get('rebounds', 0))
                win = request.POST.get('win') == 'true'
                fg_made = int(request.POST.get('field_goal_made', 0))
                fg_attempted = int(request.POST.get('field_goal_attempted', 0))
                
                # Create the GameRecord for history
                GameRecord.objects.create(
                    athlete=athlete,
                    opponent=opponent,
                    venue=venue,
                    date=date_obj.today(),
                    points=pts,
                    assists=ast,
                    rebounds=reb,
                    win=win
                )
                
                # Increment the totals in BasketballStat
                stat.points += pts
                stat.assists += ast
                stat.rebounds += reb
                stat.save()

                if fg_attempted > 0:
                    fg_pct = round((fg_made / fg_attempted) * 100, 1)
                    PerformanceRecord.objects.create(
                        athlete=athlete,
                        record_date=date_obj.today(),
                        metric='Field Goal %',
                        value=str(fg_pct)
                    )
            else:
                # Direct update of totals (if needed, e.g., from other dashboards)
                stat.points = int(request.POST.get('points', stat.points))
                stat.assists = int(request.POST.get('assists', stat.assists))
                stat.rebounds = int(request.POST.get('rebounds', stat.rebounds))
                stat.speed = float(request.POST.get('speed', stat.speed))
                stat.save()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid float/int input.'})

        # Recalculate Team Averages
        team_stats = BasketballStat.objects.all()
        count = team_stats.count()
        if count > 0:
            avg_points = sum(s.points for s in team_stats) / count
            avg_assists = sum(s.assists for s in team_stats) / count
            avg_rebounds = sum(s.rebounds for s in team_stats) / count
            avg_speed = sum(float(s.speed) for s in team_stats) / count
        else:
            avg_points = avg_assists = avg_rebounds = avg_speed = 0

        # Find new top performer
        top_stat = max(team_stats, key=lambda s: s.overall_rating(), default=None)
        top_name = top_stat.athlete.user.get_full_name() or top_stat.athlete.user.username if top_stat else "N/A"

        return JsonResponse({
            'success': True,
            'avg_points': round(avg_points, 1),
            'avg_assists': round(avg_assists, 1),
            'avg_rebounds': round(avg_rebounds, 1),
            'avg_speed': round(avg_speed, 1),
            'top_performer_name': top_name
        })
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def needs_attention(request):
    coach = Coach.objects.filter(user=request.user).first()
    athletes = _athletes_queryset_for_coach(coach) if coach else Athlete.objects.select_related("user").order_by("user__username")

    roster = []
    for a in athletes:
        att_qs = Attendance.objects.filter(athlete=a)
        total_sessions = att_qs.count()
        missed_sessions = att_qs.filter(status='Absent').count()
        if total_sessions == 0:
            # Backward-compatible fallback from historical training statuses
            done = TrainingSession.objects.filter(athlete=a, status='Completed').count()
            missed = TrainingSession.objects.filter(athlete=a, status='Missed').count()
            total_sessions = done + missed
            missed_sessions = missed

        # Fully sync with Athlete Dashboard manual Attendance Consistency overrides
        perf_rec = PerformanceRecord.objects.filter(athlete=a, metric='Attendance Consistency').order_by('-record_date', '-id').first()
        if perf_rec:
            try:
                import re
                nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(perf_rec.value))
                if nums:
                    override_pct = float(nums[0])
                    # Sync UI representation with the overridden percentage
                    base = max(total_sessions, 100) if total_sessions == 0 else total_sessions
                    total_sessions = base
                    missed_sessions = int(round(base * ((100.0 - override_pct) / 100.0)))
            except Exception:
                pass

        try:
            avatar = a.profile_picture.url if a.profile_picture else f"https://api.dicebear.com/7.x/avataaars/svg?seed={a.user.username}"
        except Exception:
            avatar = f"https://api.dicebear.com/7.x/avataaars/svg?seed={a.user.username}"

        roster.append({
            "id": a.id,
            "name": a.user.get_full_name() or a.user.username,
            "username": a.user.username,
            "imageUrl": avatar,
            "totalSessions": int(total_sessions),
            "missedSessions": int(missed_sessions),
            "position": a.position or "Player",
            "jersey": a.jersey_number or "#--",
            "grade": a.grade_level or "Active",
            "contact": a.contact_number or "N/A",
        })

    critical_threshold = 10
    critical_count = sum(1 for r in roster if r["missedSessions"] >= critical_threshold)
    team_avg_attendance = (
        round(
            (sum(max(0, r["totalSessions"] - r["missedSessions"]) for r in roster) / max(1, sum(r["totalSessions"] for r in roster)))
            * 100,
            1,
        )
        if roster
        else 100.0
    )

    context = {
        "coach": coach,
        "portal_type": "coach",
        "roster_json": roster,
        "critical_threshold": critical_threshold,
        "team_avg_attendance": team_avg_attendance,
        "critical_count": critical_count,
    }
    return render(request, "management/needs_attention.html", context)


@login_required
@require_POST
def mark_attendance(request):
    """Persist attendance marks from the high-end compliance dashboard."""
    coach = Coach.objects.filter(user=request.user).first()
    athlete_id = request.POST.get("athlete_id")
    status = (request.POST.get("status") or "").strip().lower()
    if status not in {"present", "absent"}:
        return JsonResponse({"success": False, "error": "Invalid status."}, status=400)
    try:
        athlete_id_int = int(athlete_id)
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid athlete id."}, status=400)

    athlete = get_object_or_404(Athlete, pk=athlete_id_int)

    # Keep attendance in sync with a concrete training session row.
    session = TrainingSession.objects.create(
        athlete=athlete,
        coach=coach,
        sports=(coach.sports if coach else athlete.sports or ""),
        session_date=timezone.now(),
        duration_minutes=60,
        notes="Compliance dashboard attendance mark",
        status="Completed" if status == "present" else "Missed",
    )
    Attendance.objects.create(
        athlete=athlete,
        session=session,
        status="Present" if status == "present" else "Absent",
    )

    att_qs = Attendance.objects.filter(athlete=athlete)
    total_sessions = att_qs.count()
    missed_sessions = att_qs.filter(status="Absent").count()
    attendance_rate = round(((total_sessions - missed_sessions) / total_sessions) * 100, 1) if total_sessions else 100.0

    # Sync PerformanceRecord as well to maintain backward compatibility with Top Performer view and athlete dashboard
    perf_record = PerformanceRecord.objects.filter(athlete=athlete, metric='Attendance Consistency').order_by('-record_date', '-id').first()
    if perf_record:
        perf_record.value = str(int(attendance_rate))
        perf_record.record_date = timezone.now().date()
        perf_record.save()
    else:
        PerformanceRecord.objects.create(
            athlete=athlete,
            metric='Attendance Consistency',
            value=str(int(attendance_rate)),
            record_date=timezone.now().date()
        )

    return JsonResponse(
        {
            "success": True,
            "athlete_id": athlete.id,
            "total_sessions": total_sessions,
            "missed_sessions": missed_sessions,
            "attendance_rate": attendance_rate,
        }
    )

from django.http import JsonResponse
from django.views.decorators.http import require_POST

@login_required
@require_POST
def mark_notifications_read(request):
    import json
    try:
        data = json.loads(request.body)
        ntype = data.get('type')
        if ntype == 'chat':
            Message.objects.filter(receiver=request.user, is_read=False).update(is_read=True)
        else:
            Notification.objects.filter(recipient=request.user, notification_type=ntype, is_read=False).update(is_read=True)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def _athletes_queryset_for_coach(coach):
    """Athletes visible to this coach (comma-separated sports supported)."""
    if not coach or not (coach.sports or "").strip():
        return Athlete.objects.select_related("user").order_by("user__username")
    parts = [p.strip() for p in str(coach.sports).split(",") if p.strip()]
    if len(parts) > 1:
        q = Q()
        for p in parts:
            q |= Q(sports__icontains=p)
        return (
            Athlete.objects.filter(q)
            .distinct()
            .select_related("user")
            .order_by("user__username")
        )
    return (
        Athlete.objects.filter(sports__icontains=coach.sports.strip())
        .select_related("user")
        .order_by("user__username")
    )


@login_required
def message_athlete(request):
    coach = Coach.objects.filter(user=request.user).first()
    if not coach and not request.user.is_superuser:
        messages.error(request, "Only coaches can access messaging.")
        return redirect("home")

    if coach:
        athletes = _athletes_queryset_for_coach(coach)
    else:
        athletes = Athlete.objects.select_related("user").order_by("user__username")

    roster_ids = set(athletes.values_list("id", flat=True))
    roster_user_ids = list(athletes.values_list("user_id", flat=True))

    if request.method == "POST":
        athlete_id = request.POST.get("athlete_id")
        content = (request.POST.get("message_content") or "").strip()
        if not athlete_id or not content:
            messages.warning(request, "Select an athlete and enter a message.")
            return redirect("management:message_athlete")
        try:
            aid = int(athlete_id)
        except (TypeError, ValueError):
            return redirect("management:message_athlete")
        if aid not in roster_ids:
            messages.error(request, "Invalid athlete.")
            return redirect("management:message_athlete")
        athlete = get_object_or_404(Athlete, pk=aid)
        Message.objects.create(
            sender=request.user,
            receiver=athlete.user,
            content=content,
            is_read=False,
        )
        messages.success(request, f"Message sent to {athlete.user.username}.")
        return redirect(f"{reverse('management:message_athlete')}?thread={aid}")

    selected_athlete = None
    thread_messages = []
    selected_id = request.GET.get("thread") or request.GET.get("preselect")
    if selected_id:
        try:
            sid = int(selected_id)
        except (TypeError, ValueError):
            sid = None
        if sid is not None and sid in roster_ids:
            selected_athlete = athletes.filter(pk=sid).first()
        if selected_athlete:
            Message.objects.filter(
                receiver=request.user,
                sender=selected_athlete.user,
                is_read=False,
            ).update(is_read=True)
            thread_messages = list(
                Message.objects.filter(
                    Q(sender=request.user, receiver=selected_athlete.user)
                    | Q(sender=selected_athlete.user, receiver=request.user)
                ).select_related("sender", "receiver")
                .order_by("timestamp")
            )

    unread_rows = (
        Message.objects.filter(
            receiver=request.user,
            sender_id__in=roster_user_ids,
            is_read=False,
        )
        .values("sender_id")
        .annotate(c=Count("id"))
        if roster_user_ids
        else []
    )
    unread_by_uid = {row["sender_id"]: row["c"] for row in unread_rows}

    athlete_threads = []
    for a in athletes:
        uid = a.user_id
        unread = unread_by_uid.get(uid, 0)
        last = (
            Message.objects.filter(
                Q(sender=request.user, receiver_id=uid)
                | Q(sender_id=uid, receiver=request.user)
            )
            .order_by("-timestamp")
            .first()
        )
        preview = ""
        if last:
            preview = last.content if len(last.content) <= 100 else last.content[:97] + "…"
        athlete_threads.append(
            {
                "athlete": a,
                "unread": unread,
                "last_preview": preview,
                "last_at": last.timestamp if last else None,
            }
        )

    athlete_threads.sort(
        key=lambda x: (
            -(1 if x["unread"] else 0),
            -(x["last_at"].timestamp() if x["last_at"] else 0),
        )
    )

    coach_unread_messages_count = sum(unread_by_uid.values())

    context = {
        "athletes": athletes,
        "athlete_threads": athlete_threads,
        "selected_athlete": selected_athlete,
        "thread_messages": thread_messages,
        "coach_unread_messages_count": coach_unread_messages_count,
        "portal_type": "coach",
        "in_portal": True,
    }
    return render(request, "management/message_athlete.html", context)

@login_required
def basketball_analytics(request):
    """
    Athlete analytics UI: stats come from BasketballStat (same source as coach dashboard).
    Top performer = max overall_rating() = points + assists + rebounds + speed.
    """
    coach = Coach.objects.filter(user=request.user).first()
    if coach:
        athletes_qs = Athlete.objects.filter(sports__icontains=coach.sports)
    else:
        athletes_qs = Athlete.objects.all()

    athletes_payload = []
    # Fetch all stats and athletes
    all_athletes_with_stats = []
    for athlete in athletes_qs.select_related("user"):
        stat, _ = BasketballStat.objects.get_or_create(athlete=athlete)
        all_athletes_with_stats.append((athlete, stat))
    
    # Sort by overall rating descending
    all_athletes_with_stats.sort(key=lambda x: x[1].overall_rating(), reverse=True)

    for athlete, stat in all_athletes_with_stats:
        latest_eval = Evaluation.objects.filter(athlete=athlete).order_by("-date").first()
        trend_map = {"Improving": "up", "Declining": "down", "Stable": "stable"}
        trend = trend_map.get(
            getattr(latest_eval, "speed_trend", None) or "Stable", "stable"
        )
        inj = (athlete.injury_status or "").strip().lower()
        if inj in ("none", "", "n/a", "no"):
            health = {
                "status": "Cleared",
                "note": "No active injury on file.",
                "tone": "cleared",
            }
        else:
            health = {
                "status": "Injured",
                "note": athlete.injury_status or "See medical staff.",
                "tone": "injured",
            }

        athletes_payload.append(
            {
                "id": str(athlete.id),
                "name": athlete.user.get_full_name() or athlete.user.username,
                "profile_picture": athlete.profile_picture.url if athlete.profile_picture else None,
                "role": "Athlete",
                "position": athlete.position or 'Player',
                "jersey": athlete.jersey_number or '#--',
                "grade": athlete.grade_level or 'Active',
                "stats": {
                    "l1": stat.points,
                    "l2": stat.assists,
                    "l3": stat.rebounds,
                },
                "speed": float(stat.speed),
                "trend": trend,
                "health": health,
                "observation": (
                    latest_eval.notes
                    if latest_eval
                    else "No evaluation notes yet."
                ),
            }
        )

    # Determine sport labels
    sport_type = 'Basketball'
    coach_sports_str = str(coach.sports or "").lower() if coach else ""
    if 'vol' in coach_sports_str: # Handles Volleyball, Voellyball, etc.
        sport_type = 'Volleyball'
    elif 'sepak' in coach_sports_str:
        sport_type = 'Sepak Takraw'
    
    if sport_type == 'Volleyball':
        label1, label2, label3 = 'Aces', 'Kills', 'Blocks'
        sport_icon = 'volleyball'
    elif sport_type == 'Sepak Takraw':
        label1, label2, label3 = 'Spikes', 'Serves', 'Blocks'
        sport_icon = 'circle-dashed'
    else:
        # Fallback to checking first athlete's sport if coach sport is ambiguous
        first_athlete = athletes_qs.first()
        athlete_sport = str(first_athlete.sports or "").lower() if first_athlete else ""
        if 'vol' in athlete_sport:
            label1, label2, label3 = 'Aces', 'Kills', 'Blocks'
            sport_icon = 'volleyball'
        elif 'sepak' in athlete_sport:
            label1, label2, label3 = 'Spikes', 'Serves', 'Blocks'
            sport_icon = 'circle-dashed'
        else:
            label1, label2, label3 = 'Points', 'Assists', 'Rebounds'
            sport_icon = 'trophy'

    return render(
        request,
        "management/basketball_analytics.html",
        {
            "portal_type": "coach",
            "athletes_data": athletes_payload,
            "stat_labels": {"l1": label1, "l2": label2, "l3": label3},
            "sport_icon": sport_icon,
        },
    )

@login_required
def log_incident(request):
    coach = Coach.objects.filter(user=request.user).first()
    if request.method == 'POST':
        athlete_id = request.POST.get('athlete_id')
        description = request.POST.get('description')
        date_str = request.POST.get('date')
        athlete = get_object_or_404(Athlete, id=athlete_id)
        
        Incident.objects.create(
            athlete=athlete,
            coach=coach,
            description=description,
            date=date_str
        )
        messages.success(request, "Incident submitted.")
        return redirect('management:log_incident')
        
    athletes = Athlete.objects.all() if not coach else Athlete.objects.filter(sports__icontains=coach.sports)
    
    context = {
        'athletes': athletes,
        'portal_type': 'coach'
    }
    return render(request, 'management/log_incident.html', context)

@login_required
def player_comparison(request):
    athlete1_id = request.GET.get('athlete1')
    athlete2_id = request.GET.get('athlete2')
    
    coach = Coach.objects.filter(user=request.user).first()
    athletes = Athlete.objects.all() if not coach else Athlete.objects.filter(sports__icontains=coach.sports)
    
    # Determine sport labels
    sport_type = 'Basketball'
    coach_sports_str = str(coach.sports or "").lower() if coach else ""
    if 'vol' in coach_sports_str:
        sport_type = 'Volleyball'
    elif 'sepak' in coach_sports_str:
        sport_type = 'Sepak Takraw'
    
    if sport_type == 'Volleyball':
        l1, l2, l3 = 'Aces', 'Kills', 'Blocks'
    elif sport_type == 'Sepak Takraw':
        l1, l2, l3 = 'Spikes', 'Serves', 'Blocks'
    else:
        # Fallback
        first_athlete = athletes.first()
        athlete_sport = str(first_athlete.sports or "").lower() if first_athlete else ""
        if 'vol' in athlete_sport:
            l1, l2, l3 = 'Aces', 'Kills', 'Blocks'
        elif 'sepak' in athlete_sport:
            l1, l2, l3 = 'Spikes', 'Serves', 'Blocks'
        else:
            l1, l2, l3 = 'Points', 'Assists', 'Rebounds'

    comparison_data = None
    if athlete1_id and athlete2_id:
        a1 = get_object_or_404(Athlete, id=athlete1_id)
        a2 = get_object_or_404(Athlete, id=athlete2_id)
        stat1 = BasketballStat.objects.filter(athlete=a1).first()
        stat2 = BasketballStat.objects.filter(athlete=a2).first()
        
        comparison_data = {
            'a1': a1,
            'a2': a2,
            'stat1': stat1,
            'stat2': stat2
        }

    context = {
        'athletes': athletes,
        'comparison_data': comparison_data,
        'portal_type': 'coach',
        'stat_labels': {'l1': l1, 'l2': l2, 'l3': l3}
    }
    return render(request, 'management/player_comparison.html', context)

from django.http import JsonResponse

@login_required
def update_coach_bio(request):
    if request.method == 'POST':
        coach = Coach.objects.filter(user=request.user).first()
        if coach:
            coach.bio = request.POST.get('bio')
            coach.career_milestones = request.POST.get('milestones')
            coach.save()
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
def update_coach_notifs(request):
    if request.method == 'POST':
        coach = Coach.objects.filter(user=request.user).first()
        if coach:
            coach.push_alerts = request.POST.get('push_alerts') == 'true'
            coach.weekly_reports = request.POST.get('weekly_reports') == 'true'
            coach.injury_alerts = request.POST.get('injury_alerts') == 'true'
            coach.save()
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
def update_coach_photo(request):
    if request.method == 'POST' and request.FILES.get('profile_picture'):
        coach = Coach.objects.filter(user=request.user).first()
        if coach:
            coach.profile_picture = request.FILES['profile_picture']
            coach.save()
            return JsonResponse({
                'success': True, 
                'url': coach.profile_picture.url
            })
    return JsonResponse({'success': False, 'message': 'No file uploaded'})
