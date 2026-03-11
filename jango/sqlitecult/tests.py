from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

import json

from .constants import CHART_TYPES
from .models import Dashboard, DashboardChart


class DashboardChartResizeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret123')
        self.client.force_login(self.user)
        self.dashboard = Dashboard.objects.create(user=self.user, name='Main Dashboard')
        self.chart = DashboardChart.objects.create(
            user=self.user,
            dashboard=self.dashboard,
            title='Sales by Region',
            database_name='sample.db',
            query='SELECT region, total FROM sales',
            chart_type='bar',
            chart_width=640,
            chart_height=360,
        )

    def test_create_chart_uses_default_chart_dimensions(self):
        response = self.client.post(reverse('create_chart'), {
            'dashboard_id': self.dashboard.id,
            'title': 'Orders by Status',
            'database_name': 'sample.db',
            'query': 'SELECT status, COUNT(*) AS total FROM orders GROUP BY status',
            'chart_type': 'pie',
            'auto_refresh': 0,
        })

        self.assertRedirects(response, reverse('dashboard_detail', args=[self.dashboard.id]))
        created_chart = DashboardChart.objects.get(title='Orders by Status')
        self.assertEqual(created_chart.chart_width, DashboardChart.DEFAULT_CHART_WIDTH)
        self.assertEqual(created_chart.chart_height, DashboardChart.DEFAULT_CHART_HEIGHT)

    def test_resize_endpoint_updates_chart_dimensions(self):
        response = self.client.post(
            reverse('resize_chart', args=[self.chart.id]),
            data=json.dumps({'width': 820, 'height': 480}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.chart.refresh_from_db()
        self.assertEqual(self.chart.chart_width, 820)
        self.assertEqual(self.chart.chart_height, 480)

    def test_dashboard_template_uses_inline_chart_dimensions(self):
        self.chart.chart_width = 820
        self.chart.chart_height = 480
        self.chart.save(update_fields=['chart_width', 'chart_height'])

        response = self.client.get(reverse('dashboard_detail', args=[self.dashboard.id]))

        self.assertContains(response, 'style="width: 820px; height: 480px;"')

    def test_chart_type_choices_include_number_and_table(self):
        chart_type_values = {value for value, _label in CHART_TYPES}

        self.assertIn('number', chart_type_values)
        self.assertIn('table', chart_type_values)
        self.assertIn('funnel', chart_type_values)
