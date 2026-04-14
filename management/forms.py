from django import forms
from django.contrib.auth.models import User
from .models import Athlete, Coach, TrainingSession, Payment, PerformanceRecord, Evaluation, Goal

class UserCreationByAdminForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Email already registered.")
        return email

class UserUpdateByCoachForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Email already registered.")
        return email

SPORTS_CHOICES = [
    ('Basketball', 'Basketball'),
    ('Volleyball', 'Volleyball'),
    ('Sepak Takraw', 'Sepak Takraw'),
]

class CoachForm(forms.ModelForm):
    sports_selection = forms.ChoiceField(
        choices=SPORTS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Sport Assignment"
    )

    class Meta:
        model = Coach
        fields = ['profile_picture', 'specialization', 'contact_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.sports:
            self.fields['sports_selection'].initial = self.instance.sports

    def save(self, commit=True):
        coach = super().save(commit=False)
        coach.sports = self.cleaned_data.get('sports_selection', '')
        if commit:
            coach.save()
        return coach

class AthleteForm(forms.ModelForm):
    sports_selection = forms.MultipleChoiceField(
        choices=SPORTS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Sports"
    )

    class Meta:
        model = Athlete
        fields = ['profile_picture', 'contact_number', 'address', 'weight', 'height', 'endurance_level', 'injury_status', 'jersey_number', 'position', 'grade_level']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.sports:
            self.fields['sports_selection'].initial = self.instance.sports.split(',')

    def clean_sports_selection(self):
        selection = self.cleaned_data.get('sports_selection')
        if selection and len(selection) > 1:
            raise forms.ValidationError("Select 1 Sport Only")
        return selection

    def save(self, commit=True):
        athlete = super().save(commit=False)
        athlete.sports = ','.join(self.cleaned_data['sports_selection'])
        if commit:
            athlete.save()
        return athlete

class EvaluationForm(forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = ['notes', 'speed_trend', 'strength_trend', 'attendance_rate']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ['title', 'target_value', 'current_value', 'status', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

class AthleteProfileForm(forms.ModelForm):
    sports_selection = forms.MultipleChoiceField(
        choices=SPORTS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Sports"
    )

    class Meta:
        model = Athlete
        fields = ['profile_picture', 'contact_number', 'address']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.sports:
            self.fields['sports_selection'].initial = self.instance.sports.split(',')

    def clean_sports_selection(self):
        selection = self.cleaned_data.get('sports_selection')
        if selection and len(selection) > 1:
            raise forms.ValidationError("Select 1 Sport Only")
        return selection

    def save(self, commit=True):
        athlete = super().save(commit=False)
        athlete.sports = ','.join(self.cleaned_data['sports_selection'])
        if commit:
            athlete.save()
        return athlete

class PerformanceRecordForm(forms.ModelForm):
    class Meta:
        model = PerformanceRecord
        fields = ['metric', 'value', 'record_date']
        widgets = {
            'record_date': forms.DateInput(attrs={'type': 'date'}),
        }

class TrainingSessionForm(forms.ModelForm):
    sports_selection = forms.ChoiceField(
        choices=[('', '---------')] + SPORTS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label="Sports"
    )

    class Meta:
        model = TrainingSession
        fields = ['athlete', 'sports_selection', 'session_date', 'duration_minutes', 'notes', 'status']
        widgets = {
            'session_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.sports:
            self.fields['sports_selection'].initial = self.instance.sports
        
        # Allow selecting "All Athletes"
        self.fields['athlete'].required = False
        self.fields['athlete'].empty_label = "Select All Athletes"

    def save(self, commit=True):
        session = super().save(commit=False)
        session.sports = self.cleaned_data.get('sports_selection', '')
        if commit:
            session.save()
        return session

class PaymentForm(forms.ModelForm):
    sports_selection = forms.ChoiceField(
        choices=[('', '---------')] + SPORTS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label="Sports"
    )

    class Meta:
        model = Payment
        fields = ['athlete', 'sports_selection', 'amount', 'payment_method', 'transaction_id']
        widgets = {
            'payment_method': forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_method'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.sports:
            self.fields['sports_selection'].initial = self.instance.sports

    def save(self, commit=True):
        payment = super().save(commit=False)
        payment.sports = self.cleaned_data.get('sports_selection', '')
        if commit:
            payment.save()
        return payment
