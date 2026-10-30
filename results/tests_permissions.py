"""Kurasa za /shule/ hazipaswi kumvunja mtumiaji wa mfumo mkuu."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class ResultsAccessTests(TestCase):
    databases = {'default', 'results'}

    def test_main_site_user_is_sent_to_results_login(self):
        User = get_user_model()
        user = User.objects.create_user(email='mwalimu@eutendaji.moe.go.tz', password='x')
        client = Client()
        client.force_login(user)

        response = client.get(reverse('home'))

        self.assertRedirects(response, reverse('results_login'), fetch_redirect_response=False)

    def test_anonymous_user_is_sent_to_results_login(self):
        response = Client().get(reverse('home'))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('results_login')))
