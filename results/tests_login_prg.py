"""Login ya /shule/ingia/ hufuata Post/Redirect/Get (PRG).

Kabla ya fix, kila POST isiyo-thibitisha (email haipo, password mbaya, reset
yenye hitilafu) ilirender ukurasa wa login moja kwa moja kutoka POST hiyo.
Basi mtumiaji akibonyeza F5 / back, browser ilionyesha "Confirm form
resubmission" na kujaribu kure-POST vitambulisho vile vile. Kanuni mpya:
POST zote zinarudisha redirect (302) kwa GET URL ya login; GET ndiyo
inayorender. Hii tes inahakikisha kila POST inarudi 302 — kamwe si 200.
"""
from django.test import TestCase
from django.urls import reverse

from results.models import School, TeacherAccount

LOGIN_URL = reverse('results_login')


class LoginPrgTests(TestCase):
    databases = {'default', 'results'}

    def setUp(self):
        self.school = School.objects.create(name='Mfano Secondary', region='Kagera', district='Kyerwa')
        self.academic = TeacherAccount.objects.create(
            email='mkuu@example.com', full_name='Mkuu wa Taaluma',
            role=TeacherAccount.ROLE_ACADEMIC, school=self.school,
        )
        self.academic.set_password('NenoKali#123')
        self.academic.save(using='results')

    def _unactivated(self, email='mpya@example.com'):
        a = TeacherAccount.objects.create(email=email, full_name='Mpya', school=self.school)
        a.set_unusable_password()  # is_activated = has_usable_password() = False
        a.save(using='results')
        return a

    def test_post_never_renders_200_it_always_redirects(self):
        """Kila POST kwenye login ni redirect — ndiyo kiini cha PRG."""
        cases = [
            # (data, description)
            ({'step': 'email', 'email': 'haipo@example.com'}, 'email haipo'),
            ({'step': 'email', 'email': self.academic.email}, 'email sahihi → step login'),
            ({'step': 'forgot_email', 'email': 'haipo@example.com'}, 'forgot_email email haipo'),
            ({'step': 'login', 'email': self.academic.email, 'password': 'siri-mbaya'}, 'password mbaya'),
        ]
        for data, label in cases:
            with self.subTest(label=label):
                r = self.client.post(LOGIN_URL, data)
                self.assertIn(r.status_code, (302, 301), f'{label}: POST ikarender 200, sio redirect')
                self.assertNotEqual(r.status_code, 200)

        # activate: password zisizofanana → redirect, si render
        unactivated = self._unactivated()
        r = self.client.post(LOGIN_URL, {
            'step': 'activate', 'email': unactivated.email,
            'password1': 'NenoKali#123', 'password2': 'Tofauti#456',
        })
        self.assertEqual(r.status_code, 302)

        # activate: email isiyopo → redirect
        r = self.client.post(LOGIN_URL, {
            'step': 'activate', 'email': 'haipo@example.com',
            'password1': 'NenoKali#123', 'password2': 'NenoKali#123',
        })
        self.assertEqual(r.status_code, 302)

    def _post_to_redirect(self, data):
        """POST kisha vuta redirect mara moja tu.

        Hatutumii assertRedirects kwa sababu kwake default
        fetch_redirect_response=True ina-follow redirect hiyo yenyewe —
        GET hiyo ya automatic inapop session ''login_step'' na ku-consume
        messages, basi GET yetu ya pili inaona session tupu.
        """
        r = self.client.post(LOGIN_URL, data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, LOGIN_URL)
        return r

    def test_failed_email_redirects_to_get_with_message(self):
        r = self._post_to_redirect({'step': 'email', 'email': 'haipo@example.com'})

        html = self.client.get(r.url).content.decode()
        self.assertIn('Email hii haipo kwenye mfumo', html)

    def test_valid_email_leads_to_password_step_via_get(self):
        r = self._post_to_redirect({'step': 'email', 'email': self.academic.email})

        html = self.client.get(r.url).content.decode()
        self.assertIn('Welcome back', html)                   # step='login' iko
        self.assertIn('name="step" value="login"', html)

    def test_wrong_password_redirects_and_keeps_email(self):
        r = self._post_to_redirect({
            'step': 'login', 'email': self.academic.email, 'password': 'siri-mbaya',
        })

        html = self.client.get(r.url).content.decode()
        self.assertIn('Email au password si sahihi', html)
        self.assertIn('Welcome back', html)                   # bado kwenye step login
        self.assertIn(self.academic.email, html)              # email bado imejazwa

    def test_correct_password_logs_in_and_redirects(self):
        r = self.client.post(LOGIN_URL, {
            'step': 'login', 'email': self.academic.email, 'password': 'NenoKali#123',
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse('academic_dashboard'))
        self.assertTrue(r.wsgi_request.user.is_authenticated)

    def test_register_school_link_still_on_plain_get(self):
        html = self.client.get(LOGIN_URL).content.decode()
        self.assertIn(reverse('register_school_start'), html)

    def test_login_get_is_never_cached(self):
        """Ukurasa wa login usijazwe mkononi kwenye cache za browser/proxy.

        Ukurasa wa login uki-cached, browser inaweza kukabidhi nakala ya
        zamani yenye csrf token ya kale wakati cookie ya csrftoken imebadilika —
        hiyo ndiyo chanzo cha '403 CSRF verification failed' wakati wa login
        (token ya fomu hailingani na cookie ya sasa). lazima 'no-store' iwepo.
        """
        r = self.client.get(LOGIN_URL)
        cache_control = r.headers.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)
        self.assertIn('no-cache', cache_control)