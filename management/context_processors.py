from django.db.models import Q
from .models import Message, Notification

def unread_notifications(request):
    if not request.user.is_authenticated:
        return {}
        
    counts = {
        'total': 0,
        'chat': Message.objects.filter(receiver=request.user, is_read=False).count(),
        'payment': 0,
        'session': 0,
        'evaluation': 0,
        'incident': 0,
        'goal': 0,
        'system': 0,
    }
    
    notifications = Notification.objects.filter(recipient=request.user, is_read=False)
    
    for n in notifications:
        n_type = n.notification_type.lower()
        if n_type in counts:
            counts[n_type] += 1
        else:
            counts['system'] += 1
            
    counts['total'] = sum(v for k, v in counts.items() if k != 'total')
    
    return {'unread_counts': counts}
