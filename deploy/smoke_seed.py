"""Synthetic fixtures, only for an empty, explicitly named CI smoke database.

Run through manage.py shell. Never run this against the team's demo database.
"""
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from accounts.models import Profile, Role
from committees.models import Committee, CommitteeMember
from meetings.models import ActionItem, MeetingDraft
from tasks.services import create_task

assert settings.DATABASES['default']['NAME'] == 'orgflow_deployment_smoke'
User = get_user_model()
assert not User.objects.exists(), 'Smoke seed requires an empty database.'
users = {}
for name, role in [('officer', Role.OFFICER), ('member', Role.MEMBER), ('outsider', Role.MEMBER), ('reset', Role.MEMBER)]:
    user = User.objects.create_user(username=f'smoke_{name}', email=f'{name}@example.invalid', password='Synthetic-Smoke-2026!')
    Profile.objects.update_or_create(user=user, defaults={'role': role})
    users[name] = user
committee = Committee.objects.create(name='Synthetic deployment committee', created_by=users['officer'])
CommitteeMember.objects.create(committee=committee, user=users['member'])
task = create_task(users['officer'], title='Synthetic deployment claim', committee=committee)
draft = MeetingDraft.objects.create(title='Synthetic approved import fixture', notes='Synthetic fixture; no AI provider called.', created_by=users['officer'])
ActionItem.objects.create(draft=draft, description='Prepare synthetic integration checklist', accepted=True, position=0)
ActionItem.objects.create(draft=draft, description='Excluded synthetic action', accepted=False, position=1)
draft.review(users['officer'], 'approved', expected_generation='')
print('SMOKE_FIXTURE=' + json.dumps({'task': str(task.pk), 'draft': str(draft.pk), 'member': str(users['member'].pk)}))
