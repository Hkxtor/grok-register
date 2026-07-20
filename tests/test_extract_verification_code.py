"""回归：邮件验证码提取必须优先真实 confirmation code，而不是 CSS/噪声 token。"""

import unittest

from mail_service import extract_verification_code


class ExtractVerificationCodeTests(unittest.TestCase):
    def test_spacexai_subject_with_per100_body_noise(self):
        """Cloud Mail 实况：主题含 VJ6-YE7，正文含 per-100，绝不能填 per-100。"""
        subject = "SpaceXAI confirmation code: VJ6-YE7"
        body = (
            '<div class="per-100">footer</div> tracking per-100 '
            "Your account signup details"
        )
        self.assertEqual(
            extract_verification_code(body, subject),
            "VJ6-YE7",
        )

    def test_classic_subject_prefix_xai(self):
        self.assertEqual(
            extract_verification_code("hello", "VJ6-YE7 xAI"),
            "VJ6-YE7",
        )

    def test_body_confirmation_code_hyphenated(self):
        self.assertEqual(
            extract_verification_code(
                "Your confirmation code: AB1-CD2 is valid for 10 minutes",
                "",
            ),
            "AB1-CD2",
        )

    def test_rejects_bare_per100_noise_when_no_real_code(self):
        self.assertIsNone(extract_verification_code("class=per-100 width max-100", ""))

    def test_digit_verification_code_still_works(self):
        self.assertEqual(
            extract_verification_code("Your verification code: 482916", ""),
            "482916",
        )

    def test_labeled_code_beats_earlier_noise_token(self):
        body = "per-100\nconfirmation code: VJ6-YE7\n"
        self.assertEqual(extract_verification_code(body, ""), "VJ6-YE7")

    def test_labeled_per100_noise_is_rejected(self):
        self.assertIsNone(
            extract_verification_code("confirmation code: per-100", "")
        )


if __name__ == "__main__":
    unittest.main()
