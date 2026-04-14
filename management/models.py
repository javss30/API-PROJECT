import re
from django.db import models
from django.contrib.auth.models import User

class Athlete(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    contact_number = models.CharField(max_length=15)
    address = models.TextField()
    
    # Physical Condition
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Weight in kg")
    height = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Height in cm")
    endurance_level = models.CharField(max_length=50, default='Medium', choices=[('Low', 'Low'), ('Medium', 'Medium'), ('High', 'High'), ('Elite', 'Elite')])
    injury_status = models.CharField(max_length=100, default='None', help_text="Current injury or 'None'")
    sports = models.TextField(null=True, blank=True, help_text="Comma-separated list of sports")
    
    # Team Details
    jersey_number = models.CharField(max_length=10, null=True, blank=True, default='#--')
    position = models.CharField(max_length=50, null=True, blank=True, default='Player')
    grade_level = models.CharField(max_length=50, null=True, blank=True, default='Active')
    
    plain_password = models.CharField(max_length=128, null=True, blank=True, help_text="Plain text password (Admin access only)")

    def __str__(self):
        return self.user.username

class Evaluation(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='evaluations')
    coach = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(help_text="Coach Evaluation/Notes")
    speed_trend = models.CharField(max_length=20, choices=[('Improving', 'Improving'), ('Stable', 'Stable'), ('Declining', 'Declining')], default='Stable')
    strength_trend = models.CharField(max_length=20, choices=[('Improving', 'Improving'), ('Stable', 'Stable'), ('Declining', 'Declining')], default='Stable')
    attendance_rate = models.IntegerField(default=100, help_text="Percentage 0-100")

    def __str__(self):
        return f"Evaluation for {self.athlete.user.username} on {self.date}"

class Goal(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='goals')
    title = models.CharField(max_length=200, help_text="e.g., Basket count")
    target_value = models.CharField(max_length=100, help_text="e.g., 15pts")
    current_value = models.CharField(max_length=100, help_text="e.g., 10pts")
    status = models.CharField(max_length=50, choices=[('In Progress', 'In Progress'), ('Achieved', 'Achieved'), ('On Hold', 'On Hold')], default='In Progress')
    due_date = models.DateField(null=True, blank=True)

    def progress_percentage(self):
        try:
            current_nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(self.current_value))
            target_nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(self.target_value))
            
            if not current_nums or not target_nums:
                return 0
                
            current = float(current_nums[0])
            target = float(target_nums[0])
            
            if target <= 0: return 0
            
            percentage = (current / target) * 100
            return min(round(percentage), 100)
        except (IndexError, ValueError, ZeroDivisionError):
            return 0

    def __str__(self):
        return f"{self.title} for {self.athlete.user.username}"

class Coach(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(upload_to='coach_pics/', null=True, blank=True)
    specialization = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15)
    sports = models.TextField(null=True, blank=True, help_text="Comma-separated list of sports")
    plain_password = models.CharField(max_length=128, null=True, blank=True, help_text="Plain text password (Admin access only)")
    
    # New fields for Coach Identity
    bio = models.TextField(null=True, blank=True)
    experience_years = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0)
    career_milestones = models.TextField(null=True, blank=True, help_text="Semicolon-separated list of milestones")
    
    # Notification Settings
    push_alerts = models.BooleanField(default=True)
    weekly_reports = models.BooleanField(default=True)
    injury_alerts = models.BooleanField(default=True)

    def __str__(self):
        return self.user.username

class TrainingSession(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    coach = models.ForeignKey(Coach, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    sports = models.TextField(null=True, blank=True, help_text="Sport for this session")
    session_date = models.DateTimeField()
    duration_minutes = models.IntegerField(default=60)
    notes = models.TextField()
    status = models.CharField(max_length=20, choices=[('Scheduled', 'Scheduled'), ('Completed', 'Completed'), ('Missed', 'Missed')], default='Scheduled')

    def __str__(self):
        return f"Session for {self.athlete.user.username} on {self.session_date}"

class Payment(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    sports = models.TextField(null=True, blank=True, help_text="Sport for this payment")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=100, unique=True)
    payment_method = models.CharField(max_length=50, choices=[
        ('Over-the-counter', 'Over-the-counter'),
        ('GCash', 'GCash'),
        ('BDO', 'BDO'),
        ('Metrobank', 'Metrobank')
    ], default='Over-the-counter')

    def __str__(self):
        return f"{self.athlete.user.username} - {self.amount}"

class PerformanceRecord(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    record_date = models.DateField()
    metric = models.CharField(max_length=100)
    value = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.athlete.user.username} - {self.metric}: {self.value}"

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    notification_type = models.CharField(max_length=50, default='payment') # e.g., 'payment', 'system', 'injury', 'performance', 'session', 'evaluation', 'goal', 'incident'

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class Team(models.Model):
    name = models.CharField(max_length=100)
    coach = models.ForeignKey(Coach, on_delete=models.SET_NULL, null=True, related_name='teams')
    sport = models.CharField(max_length=50, choices=[('Basketball', 'Basketball'), ('Volleyball', 'Volleyball'), ('Sepak Takraw', 'Sepak Takraw')])
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def win_loss_ratio(self):
        total = self.wins + self.losses
        if total == 0: return 0
        return round((self.wins / total) * 100, 1)

    def __str__(self):
        return f"{self.name} ({self.sport})"

class Attendance(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='attendance_records')
    session = models.ForeignKey(TrainingSession, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField(max_length=20, choices=[('Present', 'Present'), ('Absent', 'Absent'), ('Excused', 'Excused')], default='Present')
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.athlete.user.username} - {self.session.session_date} - {self.status}"

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

class Announcement(models.Model):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='announcements')
    sport = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class BasketballStat(models.Model):
    athlete = models.OneToOneField(Athlete, on_delete=models.CASCADE, related_name='basketball_stats')
    points = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    rebounds = models.IntegerField(default=0)
    speed = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    def overall_rating(self):
        # Rank primarily by points (scores) as requested by user
        return self.points + (self.assists * 0.1) + (self.rebounds * 0.1) + (float(self.speed) * 0.01)

    def __str__(self):
        return f"{self.athlete.user.username} - Pts: {self.points}, Ast: {self.assists}"

class GameRecord(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='game_records')
    opponent = models.CharField(max_length=200)
    venue = models.CharField(max_length=200)
    date = models.DateField()
    points = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    rebounds = models.IntegerField(default=0)
    win = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.athlete.user.username} vs {self.opponent} ({self.date})"

class Incident(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name='incidents')
    coach = models.ForeignKey(Coach, on_delete=models.SET_NULL, null=True)
    description = models.TextField()
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Incident for {self.athlete.user.username} on {self.date}"

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Payment)
def notify_payment(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.athlete.user,
            title="New Payment Recorded",
            message=f"A payment of {instance.amount} was recorded via {instance.payment_method}.",
            notification_type='payment'
        )

@receiver(post_save, sender=TrainingSession)
def notify_session(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.athlete.user,
            title="New Training Session",
            message=f"A new session is scheduled for {instance.session_date.strftime('%Y-%m-%d %H:%M')}.",
            notification_type='session'
        )
        if instance.coach:
            Notification.objects.create(
                recipient=instance.coach.user,
                title="New Training Session",
                message=f"A new session has been scheduled with {instance.athlete.user.username}.",
                notification_type='session'
            )

@receiver(post_save, sender=Evaluation)
def notify_evaluation(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.athlete.user,
            title="New Coach Evaluation",
            message="Your coach has submitted a new evaluation for you.",
            notification_type='evaluation'
        )

@receiver(post_save, sender=Goal)
def notify_goal(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.athlete.user,
            title="New Goal Assigned",
            message=f"A new goal '{instance.title}' has been assigned to you.",
            notification_type='goal'
        )

@receiver(post_save, sender=Incident)
def notify_incident(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.athlete.user,
            title="New Incident Report",
            message="An incident report has been logged.",
            notification_type='incident'
        )
