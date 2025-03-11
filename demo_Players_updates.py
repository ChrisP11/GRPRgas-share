import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Players

# Update Players table and set Member = 1 for every row
Players.objects.all().update(Member=1)

# Update Players table and set Member = 0 for any row where user_id is greater than 29
Players.objects.filter(user_id__gt=29).update(Member=0)

# Update Players table and set SplitPartner for specific ids
split_partner_updates = {
    1: 2,
    2: 1,
    3: 4,
    4: 3,
    5: 6,
    6: 5,
    11: 12,
    12: 11,
    21: 22,
    22: 21,
    16: 17,
    17: 16,
}

for player_id, split_partner in split_partner_updates.items():
    Players.objects.filter(id=player_id).update(SplitPartner=split_partner)

print("Players table updated successfully.")