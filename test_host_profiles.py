from __future__ import annotations

import unittest

import harvester.fetcher as fetcher


class HostProfilesTests(unittest.TestCase):
    def setUp(self) -> None:
        fetcher._HOST_PROFILES_CACHE = None

    def test_get_host_profile_returns_override_for_listed_host(self) -> None:
        profile = fetcher._get_host_profile("https://ballyclareballygowan.com/notice%20board.htm")

        self.assertEqual(profile["navigation_timeout_ms"], 60000)
        self.assertEqual(profile["max_retries"], 3)

    def test_get_host_profile_returns_defaults_for_unlisted_host(self) -> None:
        profile = fetcher._get_host_profile("https://example.org/bulletins")

        self.assertEqual(profile["navigation_timeout_ms"], 30000)
        self.assertEqual(profile["max_retries"], 2)
        self.assertEqual(profile["retry_backoff_ms"], 2000)


if __name__ == "__main__":
    unittest.main()
