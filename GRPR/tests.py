from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from GRPR.models import Players, TeeTimesInd, Courses, Crews
from datetime import datetime, timedelta

class ViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Use an existing user
        cls.user = User.objects.get(username='john.sullivan@tjmbrokerage.com')  

        # Fetch the crew associated with the user (if applicable)
        cls.crew = Crews.objects.get(name='GAS')  # Adjust as necessary

        # Fetch the player associated with the user
        cls.player = Players.objects.get(user=cls.user)

        # Create a test course
        cls.course = Courses.objects.create(courseName='The Preserve', courseTimeSlot='9:00')

        # Create test tee times
        cls.teetime1 = TeeTimesInd.objects.create(PID=cls.player, CourseID=cls.course, gDate=datetime.now() + timedelta(days=1))
        cls.teetime2 = TeeTimesInd.objects.create(PID=cls.player, CourseID=cls.course, gDate=datetime.now() + timedelta(days=2))

    def setUp(self):
        self.client = Client()
        self.client.login(username='john.sullivan@tjmbrokerage.com', password='pword1')  

    def test_schedule_view(self):
        response = self.client.get(reverse('schedule_view'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'GRPR/schedule.html')
        self.assertIn('players', response.context)
        self.assertIn('schedule', response.context)
        self.assertIn('first_name', response.context)
        self.assertIn('last_name', response.context)

        # Check if the schedule contains the correct tee times
        schedule = response.context['schedule']
        self.assertEqual(len(schedule), 2)
        self.assertEqual(schedule[0]['gDate'], self.teetime1.gDate)
        self.assertEqual(schedule[0]['courseName'], self.course.courseName)
        self.assertEqual(schedule[0]['courseTimeSlot'], self.course.courseTimeSlot)
        self.assertEqual(schedule[1]['gDate'], self.teetime2.gDate)
        self.assertEqual(schedule[1]['courseName'], self.course.courseName)
        self.assertEqual(schedule[1]['courseTimeSlot'], self.course.courseTimeSlot)

    def test_subrequest_view(self):
        # Store the tee time ID in the session
        session = self.client.session
        session['tt_id'] = self.teetime1.id
        session.save()

        response = self.client.get(reverse('subrequest_view'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'GRPR/subrequest.html')
        self.assertIn('first_name', response.context)
        self.assertIn('last_name', response.context)
        self.assertIn('gDate', response.context)
        self.assertIn('course_name', response.context)
        self.assertIn('course_time_slot', response.context)
        self.assertIn('other_players', response.context)
        self.assertIn('available_subs', response.context)

# Create your tests here.